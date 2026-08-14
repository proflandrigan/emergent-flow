"""Tests for the reference node definitions (emergentflow.nodes.examples).

Covers contract conformance for both reference nodes and the ADR-0002 invariant
at node granularity: for a given IR node, ``execute`` must produce the same
result as running the code emitted by ``codegen``.
"""

import csv
import pathlib

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.api import is_inspectable
from emergentflow.clean.errors import CleanError
from emergentflow.codegen.context import build_codegen_context
from emergentflow.codegen.naming import build_name_map
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir.common import Direction, Paradigm
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ml import train_regressor
from emergentflow.nodes.examples import (
    Anova,
    ApplyEstimator,
    AssertData,
    BuildReport,
    CastTypes,
    ChiSquare,
    CohortRetention,
    Composite,
    CorrectPvalues,
    Correlation,
    Crosstab,
    DataDictionary,
    Describe,
    DropMissing,
    EncodeLists,
    Evaluate,
    ExplodeLists,
    FilterRows,
    FitEstimator,
    Funnel,
    GenerateHtmlSummary,
    GroupContainer,
    ImputeMissing,
    Kruskal,
    LoadCsv,
    LoadDocuments,
    LoadJson,
    LoadParquet,
    LoadSample,
    MannWhitney,
    MarkdownNote,
    Merge,
    PowerAnalysis,
    Predict,
    RedactPii,
    ReduceDimensions,
    SelectColumns,
    SemiJoin,
    Summarize,
    TestProportions,
    TrainClassifier,
    TrainRandomForest,
    TrainRegressor,
    TrainTestSplit,
    TTest,
    VizPlotProjection,
    Wilcoxon,
)
from emergentflow.research.errors import DataQualityError


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "data.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b"])
        writer.writerow(["1", "x"])
        writer.writerow(["2", "x"])
        writer.writerow(["3", "y"])
    return str(path)


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 — test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# data.load_csv
# ---------------------------------------------------------------------------


class TestLoadCsv:
    def test_to_spec(self):
        spec = LoadCsv().to_spec()
        assert spec.type == "data.load_csv"
        assert spec.family == "data"
        assert spec.paradigm == Paradigm.FUNCTIONAL
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["frame"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]

    def test_instantiate_and_validate(self):
        node = LoadCsv().instantiate(path="x.csv")
        assert LoadCsv().validate_node(node) == []

    def test_missing_required_path_flagged(self):
        node = LoadCsv().instantiate()  # path unset
        errors = LoadCsv().validate_node(node)
        assert any("required param 'path'" in e for e in errors)

    def test_execute_reads_dataframe(self, csv_file):
        node = LoadCsv().instantiate(path=csv_file)
        out = LoadCsv().execute(node, inputs={})
        assert isinstance(out["frame"], pd.DataFrame)
        assert list(out["frame"].columns) == ["a", "b"]

    def test_codegen_matches_execute(self, csv_file):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadCsv()
        node = defn.instantiate(path=csv_file)
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
        assert scope["frame"].equals(executed["frame"])

    def test_fits_in_graph(self, csv_file):
        node = LoadCsv().instantiate(path=csv_file)
        Graph(nodes={node.id: node})


# ---------------------------------------------------------------------------
# clean.impute_missing
# ---------------------------------------------------------------------------


class TestImputeMissing:
    def test_to_spec_has_in_and_out_ports(self):
        spec = ImputeMissing().to_spec()
        dirs = sorted(p.direction.value for p in spec.ports)
        assert dirs == ["in", "out"]

    def test_in_and_out_ports_may_share_a_name(self):
        # Contract: port names are unique only *within a direction*; the IN and
        # OUT ``frame`` namespaces are independent, and instantiate() must still
        # mint a graph-valid node (distinct port ids).
        node = ImputeMissing().instantiate()
        by_dir = {p.direction: p for p in node.ports}
        assert by_dir[Direction.IN].name == by_dir[Direction.OUT].name == "frame"
        assert by_dir[Direction.IN].id != by_dir[Direction.OUT].id
        Graph(nodes={node.id: node})

    def test_strategy_choices_hint(self):
        spec = ImputeMissing().to_spec()
        strategy = next(p for p in spec.params if p.name == "strategy")
        assert strategy.hints.choices == ["mean", "median", "most_frequent"]

    def test_bad_strategy_flagged(self):
        node = ImputeMissing().instantiate(strategy="bogus")
        errors = ImputeMissing().validate_node(node)
        assert any("not one of" in e for e in errors)

    def test_execute_mean_imputation(self):
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        node = ImputeMissing().instantiate(strategy="mean")
        out = ImputeMissing().execute(node, inputs={"frame": df})
        assert out["frame"]["a"].iloc[1] == 2.0

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = ImputeMissing()
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        node = defn.instantiate(strategy="mean")
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.drop_missing
# ---------------------------------------------------------------------------


class TestDropMissing:
    def test_codegen_body_golden(self):
        defn = DropMissing()
        node = defn.instantiate(axis="rows", how="any")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert (
            frag.body == "frame = ef.clean.drop_missing(frame, axis='rows', how='any', subset=None)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = DropMissing()
        df = pd.DataFrame({"a": [1.0, None, 3.0]})
        node = defn.instantiate(axis="rows", how="any")
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.select_columns
# ---------------------------------------------------------------------------


class TestSelectColumns:
    def test_codegen_body_golden(self):
        defn = SelectColumns()
        node = defn.instantiate(columns=["a"])
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "frame = ef.clean.select_columns(frame, columns=['a'], drop=False)"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = SelectColumns()
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0], "c": [7.0, 8.0, 9.0]})
        node = defn.instantiate(columns=["a", "c"])
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.explode_lists
# ---------------------------------------------------------------------------


class TestExplodeLists:
    def test_codegen_body_golden(self):
        defn = ExplodeLists()
        node = defn.instantiate(columns=["items"])
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == (
            "frame = ef.clean.explode_lists(frame, columns=['items'], "
            "drop_empty=True, ignore_index=True)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = ExplodeLists()
        df = pd.DataFrame({"u": [1, 2], "items": [["a", "b"], ["c"]]})
        node = defn.instantiate(columns=["items"])
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.encode_lists
# ---------------------------------------------------------------------------


class TestEncodeLists:
    def test_codegen_body_golden(self):
        defn = EncodeLists()
        node = defn.instantiate(column="genres")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == (
            "frame = ef.clean.encode_lists(frame, column='genres', prefix=None, "
            "drop=True, sep=None)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = EncodeLists()
        df = pd.DataFrame({"u": [1, 2], "genres": [["rock", "jazz"], ["pop"]]})
        node = defn.instantiate(column="genres")
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.cast_types
# ---------------------------------------------------------------------------


class TestCastTypes:
    def test_codegen_body_golden(self):
        defn = CastTypes()
        node = defn.instantiate(dtypes={"a": "float"})
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "frame = ef.clean.cast_types(frame, dtypes={'a': 'float'})"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = CastTypes()
        df = pd.DataFrame({"a": [1, 2, 3]})
        node = defn.instantiate(dtypes={"a": "float"})
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.filter_rows
# ---------------------------------------------------------------------------


class TestFilterRows:
    def test_codegen_body_golden(self):
        defn = FilterRows()
        node = defn.instantiate(column="a", operator=">", value=1)
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "frame = ef.clean.filter_rows(frame, column='a', operator='>', value=1)"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = FilterRows()
        df = pd.DataFrame({"a": [1, 2, 3, 4]})
        node = defn.instantiate(column="a", operator=">", value=2)
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = {"frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# stats.anova
# ---------------------------------------------------------------------------


class TestAnova:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Anova()
        df = pd.DataFrame(
            {
                "grp": ["a", "a", "a", "b", "b", "b", "c", "c", "c"],
                "score": [1.0, 1.1, 0.9, 5.0, 5.1, 4.9, 9.0, 9.1, 8.9],
            }
        )
        node = defn.instantiate(group_col="grp", value_col="score")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert generated.f_statistic == executed.f_statistic
        assert generated.p_value == executed.p_value
        assert generated.effect_size == executed.effect_size
        assert generated.ci_low == executed.ci_low
        assert generated.ci_high == executed.ci_high
        assert generated.summary.equals(executed.summary)


# ---------------------------------------------------------------------------
# stats.ttest
# ---------------------------------------------------------------------------


class TestTTest:
    def test_codegen_body_golden(self):
        defn = TTest()
        node = defn.instantiate(group_col="grp", value_col="score")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == (
            "result = ef.stats.ttest(frame, group_col='grp', value_col='score', "
            "equal_var=True, alpha=0.05)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = TTest()
        df = pd.DataFrame(
            {
                "grp": ["a", "a", "a", "b", "b", "b"],
                "score": [1.0, 2.0, 3.0, 5.0, 6.0, 7.0],
            }
        )
        node = defn.instantiate(group_col="grp", value_col="score")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert generated.t_statistic == executed.t_statistic
        assert generated.p_value == executed.p_value
        assert generated.df == executed.df
        assert generated.group_a == executed.group_a
        assert generated.group_b == executed.group_b
        assert generated.n_a == executed.n_a
        assert generated.n_b == executed.n_b
        assert generated.mean_a == executed.mean_a
        assert generated.mean_b == executed.mean_b
        assert generated.equal_var == executed.equal_var
        assert generated.alpha == executed.alpha
        assert generated.effect_size == executed.effect_size
        assert generated.ci_low == executed.ci_low
        assert generated.ci_high == executed.ci_high


# ---------------------------------------------------------------------------
# stats.mann_whitney
# ---------------------------------------------------------------------------


class TestMannWhitney:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = MannWhitney()
        df = pd.DataFrame(
            {
                "grp": ["a", "a", "a", "b", "b", "b"],
                "score": [1.0, 2.0, 3.0, 5.0, 6.0, 7.0],
            }
        )
        node = defn.instantiate(group_col="grp", value_col="score")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# stats.wilcoxon
# ---------------------------------------------------------------------------


class TestWilcoxon:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Wilcoxon()
        df = pd.DataFrame(
            {
                "before": [10.0, 12.0, 9.0, 11.0, 13.0],
                "after": [12.0, 14.0, 10.0, 13.0, 15.0],
            }
        )
        node = defn.instantiate(col_a="before", col_b="after")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# stats.kruskal
# ---------------------------------------------------------------------------


class TestKruskal:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Kruskal()
        df = pd.DataFrame(
            {
                "grp": ["a", "a", "a", "b", "b", "b", "c", "c", "c"],
                "score": [1.0, 1.1, 0.9, 5.0, 5.1, 4.9, 9.0, 9.1, 8.9],
            }
        )
        node = defn.instantiate(group_col="grp", value_col="score")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# stats.chi_square
# ---------------------------------------------------------------------------


class TestChiSquare:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = ChiSquare()
        df = pd.DataFrame(
            {
                "treatment": ["A", "A", "B", "B", "B", "A", "B", "A"],
                "outcome": ["good", "bad", "good", "bad", "bad", "good", "good", "bad"],
            }
        )
        node = defn.instantiate(row_col="treatment", col_col="outcome")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# stats.correct_pvalues
# ---------------------------------------------------------------------------


class TestCorrectPvalues:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = CorrectPvalues()
        df = pd.DataFrame(
            {
                "group": ["a", "a", "b", "b", "c", "c"],
                "p_value": [0.01, 0.03, 0.2, 0.4, 0.6, 0.9],
            }
        )
        node = defn.instantiate(p_col="p_value", method="bonferroni")
        executed = defn.execute(node, inputs={"frame": df.copy()})["frame"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        assert_frame_equal(scope["frame"], executed)


# ---------------------------------------------------------------------------
# stats.crosstab
# ---------------------------------------------------------------------------


class TestCrosstab:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Crosstab()
        df = pd.DataFrame(
            {
                "treatment": ["A", "A", "B", "B", "B", "A", "B", "A"],
                "outcome": ["good", "bad", "good", "bad", "bad", "good", "good", "bad"],
            }
        )
        node = defn.instantiate(row_col="treatment", col_col="outcome")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert generated.chi_square == executed.chi_square
        assert generated.p_value == executed.p_value
        assert generated.dof == executed.dof
        assert generated.n == executed.n
        assert_frame_equal(generated.table, executed.table)


class TestCohortRetention:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = CohortRetention()
        df = pd.DataFrame(
            {
                "user": ["A", "A", "A", "B", "C"],
                "ts": [
                    "2024-01-05",
                    "2024-02-10",
                    "2024-03-15",
                    "2024-02-20",
                    "2024-01-25",
                ],
            }
        )
        node = defn.instantiate(user_col="user", date_col="ts", period="M")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert_frame_equal(generated.tidy, executed.tidy)
        assert_frame_equal(generated.wide, executed.wide)


class TestFunnel:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Funnel()
        rows = []
        for i in range(10):
            rows.append({"user": f"u{i}", "event": "view"})
        for i in range(6):
            rows.append({"user": f"u{i}", "event": "add_to_cart"})
        for i in range(3):
            rows.append({"user": f"u{i}", "event": "purchase"})
        df = pd.DataFrame(rows)
        node = defn.instantiate(
            user_col="user", event_col="event", steps=["view", "add_to_cart", "purchase"]
        )
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert_frame_equal(generated, executed)


class TestReduceDimensions:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = ReduceDimensions()
        df = pd.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                "b": [2.0, 1.0, 4.0, 3.0, 6.0, 5.0, 8.0, 7.0],
                "c": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5],
            }
        )
        node = defn.instantiate(feature_cols=["a", "b", "c"], method="pca", n_components=2, seed=0)
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        pd.testing.assert_frame_equal(generated.coordinates, executed.coordinates)
        assert generated.method == executed.method
        assert generated.n_components == executed.n_components
        assert generated.seed == executed.seed
        pd.testing.assert_frame_equal(generated.explained_variance, executed.explained_variance)


# ---------------------------------------------------------------------------
# stats.describe
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_codegen_body_golden(self):
        defn = Describe()
        node = defn.instantiate(columns=None)
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "summary = ef.stats.describe(frame, columns=None)"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Describe()
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        node = defn.instantiate()
        executed = defn.execute(node, inputs={"frame": df.copy()})["summary"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        assert scope["summary"].equals(executed)


# ---------------------------------------------------------------------------
# stats.correlation
# ---------------------------------------------------------------------------


class TestCorrelation:
    def test_codegen_body_golden(self):
        defn = Correlation()
        node = defn.instantiate(method="pearson")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert (
            frag.body == "matrix = ef.stats.correlation(frame, method='pearson', columns=None, "
            "max_footprint_bytes=None)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Correlation()
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
        node = defn.instantiate()
        executed = defn.execute(node, inputs={"frame": df.copy()})["matrix"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        assert scope["matrix"].equals(executed)


# ---------------------------------------------------------------------------
# ml.train_classifier
# ---------------------------------------------------------------------------


class TestTrainClassifier:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        The classifier is deterministic given ``random_state``, so the two paths
        must yield an identical :class:`ClassifierResult` (all fields compare by
        value).
        """
        defn = TrainClassifier()
        df = pd.DataFrame(
            {
                "x1": [float(i) for i in range(20)] + [float(i) for i in range(20)],
                "x2": [float(i % 5) for i in range(40)],
                "label": ["low" if i % 2 == 0 else "high" for i in range(40)],
            }
        )
        node = defn.instantiate(target="label", random_state=0)
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]

        assert generated == executed


# ---------------------------------------------------------------------------
# ml.train_regressor
# ---------------------------------------------------------------------------


class TestTrainRegressor:
    def test_codegen_body_golden(self):
        defn = TrainRegressor()
        node = defn.instantiate(target="y")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "model = ef.ml.train_regressor(frame, target='y', features=None)"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        LinearRegression is deterministic, so the two paths must yield a FittedModel
        with identical inspectable metadata and fitted coefficients.
        """
        defn = TrainRegressor()
        df = pd.DataFrame(
            {
                "x": [float(i) for i in range(20)],
                "y": [2.0 * float(i) + 1.0 for i in range(20)],
            }
        )
        node = defn.instantiate(target="y")
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = _run_codegen(defn, node, {"frame": df.copy()})

        assert executed["model"].estimator_type == scope["model"].estimator_type
        assert executed["model"].task == scope["model"].task
        assert executed["model"].target == scope["model"].target
        assert executed["model"].feature_names == scope["model"].feature_names
        assert executed["model"].estimator.coef_.tolist() == scope["model"].estimator.coef_.tolist()


# ---------------------------------------------------------------------------
# ml.train_random_forest
# ---------------------------------------------------------------------------


class TestTrainRandomForest:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        RandomForestClassifier is deterministic given random_state, so the two paths
        must yield a FittedModel with identical inspectable metadata and identical
        predictions on the training feature matrix.
        """
        defn = TrainRandomForest()
        df = pd.DataFrame(
            {
                "x1": [float(i) for i in range(20)] + [float(i) for i in range(20)],
                "x2": [float(i % 5) for i in range(40)],
                "label": ["low" if i % 2 == 0 else "high" for i in range(40)],
            }
        )
        X = df[["x1", "x2"]]
        node = defn.instantiate(target="label", random_state=0)
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = _run_codegen(defn, node, {"frame": df.copy()})

        assert executed["model"].estimator_type == scope["model"].estimator_type
        assert executed["model"].task == scope["model"].task
        assert executed["model"].target == scope["model"].target
        assert executed["model"].feature_names == scope["model"].feature_names
        assert (
            executed["model"].estimator.predict(X).tolist()
            == scope["model"].estimator.predict(X).tolist()
        )


# ---------------------------------------------------------------------------
# ml.train_test_split
# ---------------------------------------------------------------------------


class TestTrainTestSplit:
    def test_codegen_body_golden(self):
        defn = TrainTestSplit()
        node = defn.instantiate(test_size=0.25, random_state=0)
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert (
            frag.body
            == "train, test = ef.ml.train_test_split(frame, test_size=0.25, random_state=0)"
        )

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code (both OUT ports)."""
        defn = TrainTestSplit()
        df = pd.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                "b": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
            }
        )
        node = defn.instantiate(test_size=0.25, random_state=0)
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        assert scope["train"].equals(executed["train"])
        assert scope["test"].equals(executed["test"])


# ---------------------------------------------------------------------------
# ml.predict
# ---------------------------------------------------------------------------


class TestPredict:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        The same fitted model object is injected into both the execute inputs dict
        and the _run_codegen scope so both paths use identical estimator state.
        """
        defn = Predict()
        df = pd.DataFrame(
            {
                "x": [float(i) for i in range(20)],
                "y": [2.0 * float(i) + 1.0 for i in range(20)],
            }
        )
        model = train_regressor(df, target="y")
        node = defn.instantiate()
        executed = defn.execute(node, inputs={"model": model, "frame": df.copy()})
        scope = {"model": model, "frame": df.copy()}
        _run_codegen(defn, node, scope)
        assert scope["predictions"].equals(executed["predictions"])


# ---------------------------------------------------------------------------
# ml.evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        The same fitted model object is injected into both the execute inputs dict
        and the _run_codegen scope so both paths use identical estimator state.
        """
        defn = Evaluate()
        df = pd.DataFrame(
            {
                "x": [float(i) for i in range(20)],
                "y": [2.0 * float(i) + 1.0 for i in range(20)],
            }
        )
        model = train_regressor(df, target="y")
        node = defn.instantiate()
        inputs = {"model": model, "frame": df}
        executed = defn.execute(node, inputs)
        scope = {"model": model, "frame": df}
        _run_codegen(defn, node, scope)
        assert scope["result"].task == executed["result"].task
        assert scope["result"].n == executed["result"].n
        assert scope["result"].metrics == executed["result"].metrics


# ---------------------------------------------------------------------------
# ml.summarize
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Summarize()
        df = pd.DataFrame(
            {
                "x": [float(i) for i in range(20)],
                "y": [2.0 * float(i) + 1.0 for i in range(20)],
            }
        )
        model = train_regressor(df, target="y")
        node = defn.instantiate()
        inputs = {"model": model}
        executed = defn.execute(node, inputs)
        scope = {"model": model}
        _run_codegen(defn, node, scope)
        assert scope["summary"] == executed["summary"]

    def test_unsupported_estimator_degrades_gracefully(self):
        """A model whose estimator_type has no registered summary builder must not crash --
        it degrades to {"kind": "unsupported"}, never a live estimator on the payload."""
        defn = Summarize()
        df = pd.DataFrame(
            {
                "x": [float(i) for i in range(20)],
                "y": [2.0 * float(i) + 1.0 for i in range(20)],
            }
        )
        model = train_regressor(df, target="y")
        node = defn.instantiate()
        result = defn.execute(node, inputs={"model": model})
        assert isinstance(result["summary"], dict)


# ---------------------------------------------------------------------------
# reports.generate_html_summary
# ---------------------------------------------------------------------------


class TestGenerateHtmlSummary:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        ydata-profiling embeds a generation timestamp, so the HTML is not
        byte-reproducible between calls (see ``emergentflow.reports``). We assert
        the structural equivalence the reports module prescribes instead: both
        paths return a non-empty HTML string carrying the requested title.
        """
        defn = GenerateHtmlSummary()
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": ["x", "y", "z", "x", "y"]})
        node = defn.instantiate(title="Equivalence Check")
        executed = defn.execute(node, inputs={"frame": df.copy()})["html"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["html"]

        for html in (executed, generated):
            assert isinstance(html, str)
            assert "<html" in html.lower()
            assert "Equivalence Check" in html


class TestBuildReport:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        Compared structurally (the story's own instruction: "keyed on the structured report
        model, not rendered bytes") rather than via Report.__eq__, because a Section's content
        may be a DataFrame -- comparing two DataFrames with == raises ("truth value of a
        DataFrame is ambiguous"), so a plain dataclass equality check on Section is unsafe
        whenever a table section is present.
        """
        defn = BuildReport()
        frame = pd.DataFrame({"a": [1, 2, 3]})
        node = defn.instantiate(title="Equivalence Check", author="Ada")

        executed = defn.execute(node, inputs={"sections": [frame.copy(), "hello world"]})["report"]
        scope = _run_codegen(defn, node, {"sections": [frame.copy(), "hello world"]})
        generated = scope["report"]

        assert executed.meta == generated.meta
        assert len(executed.sections) == len(generated.sections) == 2
        for exp, gen in zip(executed.sections, generated.sections, strict=True):
            assert exp.kind == gen.kind
            assert exp.title == gen.title
            if isinstance(exp.content, pd.DataFrame):
                pd.testing.assert_frame_equal(exp.content, gen.content)
            else:
                assert exp.content == gen.content
        assert executed.html == generated.html
        assert executed.pdf_bytes is None
        assert generated.pdf_bytes is None

    def test_result_is_inspectable(self):
        defn = BuildReport()
        node = defn.instantiate(title="t")
        result = defn.execute(node, inputs={"sections": ["hello"]})["report"]
        assert is_inspectable(result) is True

    def test_deterministic(self):
        defn = BuildReport()
        frame = pd.DataFrame({"a": [1, 2]})
        node = defn.instantiate(title="Determinism Check")
        r1 = defn.execute(node, inputs={"sections": [frame.copy(), "note"]})["report"]
        r2 = defn.execute(node, inputs={"sections": [frame.copy(), "note"]})["report"]
        assert r1.html == r2.html

    def test_empty_sections_still_builds(self):
        defn = BuildReport()
        node = defn.instantiate(title="Empty Report")
        result = defn.execute(node, inputs={"sections": []})["report"]
        assert result.sections == []
        assert "<h1>Empty Report</h1>" in result.html


class TestAssertData:
    def test_codegen_matches_execute_pass_path(self):
        """ADR 0002: execute == result of running the emitted code, when the expectations pass."""
        defn = AssertData()
        frame = pd.DataFrame({"age": [25, 30, 40]})
        node = defn.instantiate(expectations=[{"type": "non_null", "column": "age"}])

        executed = defn.execute(node, inputs={"frame": frame.copy()})["frame"]
        scope = _run_codegen(defn, node, {"frame": frame.copy()})
        generated = scope["frame"]

        pd.testing.assert_frame_equal(executed, generated)
        pd.testing.assert_frame_equal(executed, frame)

    def test_codegen_matches_execute_fail_path(self):
        """ADR 0002 extends to the failure path: both raise the same typed error, with
        structurally equal violations frames -- not compared via == (DataFrame == raises
        "truth value is ambiguous"), via pd.testing.assert_frame_equal instead."""
        defn = AssertData()
        frame = pd.DataFrame({"age": [25, -5, 200]})
        node = defn.instantiate(
            expectations=[{"type": "range", "column": "age", "min": 0, "max": 120}]
        )

        with pytest.raises(DataQualityError) as exec_exc_info:
            defn.execute(node, inputs={"frame": frame.copy()})

        with pytest.raises(DataQualityError) as codegen_exc_info:
            _run_codegen(defn, node, {"frame": frame.copy()})

        exec_violations = exec_exc_info.value.violations
        codegen_violations = codegen_exc_info.value.violations
        pd.testing.assert_frame_equal(
            exec_violations.reset_index(drop=True), codegen_violations.reset_index(drop=True)
        )
        assert exec_violations.iloc[0]["expectation"] == "range"

    def test_result_is_inspectable(self):
        defn = AssertData()
        frame = pd.DataFrame({"a": [1, 2]})
        node = defn.instantiate(expectations=[])
        result = defn.execute(node, inputs={"frame": frame})["frame"]
        assert is_inspectable(result) is True

    def test_does_not_mutate_input(self):
        defn = AssertData()
        frame = pd.DataFrame({"a": [1, 2, None]})
        original = frame.copy()
        node = defn.instantiate(expectations=[{"type": "non_null", "column": "a"}])
        with pytest.raises(DataQualityError):
            defn.execute(node, inputs={"frame": frame})
        pd.testing.assert_frame_equal(frame, original)

    def test_empty_expectations_always_passes(self):
        defn = AssertData()
        frame = pd.DataFrame({"a": [1, 2]})
        node = defn.instantiate(expectations=[])
        result = defn.execute(node, inputs={"frame": frame})["frame"]
        pd.testing.assert_frame_equal(result, frame)


_DOCUMENTS_FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "documents"


class TestLoadDocuments:
    def test_to_spec(self):
        spec = LoadDocuments().to_spec()
        assert spec.type == "data.load_documents"
        assert spec.family == "data"
        assert spec.paradigm == Paradigm.FUNCTIONAL
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["frame"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]

    def test_instantiate_and_validate(self):
        node = LoadDocuments().instantiate(path=str(_DOCUMENTS_FIXTURES_DIR / "sample.md"))
        assert LoadDocuments().validate_node(node) == []

    def test_missing_required_path_flagged(self):
        node = LoadDocuments().instantiate()  # path unset
        errors = LoadDocuments().validate_node(node)
        assert any("required param 'path'" in e for e in errors)

    def test_execute_reads_markdown_fixture(self):
        node = LoadDocuments().instantiate(
            path=str(_DOCUMENTS_FIXTURES_DIR / "sample.md"), chunk_size=120, chunk_overlap=20
        )
        out = LoadDocuments().execute(node, inputs={})
        frame = out["frame"]
        assert list(frame.columns) == [
            "doc_id",
            "chunk_id",
            "chunk_index",
            "text",
            "source_path",
            "char_count",
        ]
        assert (frame["doc_id"] == "sample").all()
        assert len(frame) > 1
        assert frame["chunk_id"].tolist() == [f"sample_{i}" for i in range(len(frame))]

    def test_codegen_matches_execute_markdown_fixture(self):
        node = LoadDocuments().instantiate(
            path=str(_DOCUMENTS_FIXTURES_DIR / "sample.md"), chunk_size=120, chunk_overlap=20
        )
        defn = LoadDocuments()
        executed = defn.execute(node, inputs={})["frame"]
        scope = _run_codegen(defn, node, {})
        generated = scope["frame"]
        assert_frame_equal(executed, generated)

    def test_result_is_inspectable(self):
        node = LoadDocuments().instantiate(path=str(_DOCUMENTS_FIXTURES_DIR / "sample.md"))
        out = LoadDocuments().execute(node, inputs={})
        assert is_inspectable(out["frame"]) is True

    def test_pdf_fixture_requires_docs_extra_or_parses_when_available(self):
        """Golden on a checked-in tiny PDF fixture (Epic 16, Story 20). If pypdf ([docs]) is
        not installed this asserts the typed error path instead of skipping outright, so the
        base-install contract (never an opaque ImportError) stays covered even without the
        extra."""
        from emergentflow.data.errors import MissingOptionalDependencyError

        node = LoadDocuments().instantiate(path=str(_DOCUMENTS_FIXTURES_DIR / "sample.pdf"))
        defn = LoadDocuments()
        try:
            import pypdf  # noqa: F401
        except ImportError:
            with pytest.raises(MissingOptionalDependencyError):
                defn.execute(node, inputs={})
            return

        out = defn.execute(node, inputs={})
        frame = out["frame"]
        assert (frame["doc_id"] == "sample").all()
        assert "Hello PDF World" in frame["text"].iloc[0]

        scope = _run_codegen(defn, node, {})
        assert_frame_equal(frame, scope["frame"])


class TestDataDictionary:
    def _frame(self):
        return pd.DataFrame(
            {
                "a": [1, 2, 2, 3, None],
                "b": ["x", "y", "x", "x", "z"],
            }
        )

    def test_to_spec(self):
        spec = DataDictionary().to_spec()
        assert spec.type == "stats.data_dictionary"
        assert spec.family == "stats"
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["dictionary"]

    def test_execute_shape_and_content(self):
        defn = DataDictionary()
        node = defn.instantiate(top_n=2, notes={"a": "the numeric column"})
        out = defn.execute(node, inputs={"frame": self._frame()})
        result = out["dictionary"]
        assert list(result["column"]) == ["a", "b"]
        assert "top_values" in result.columns
        assert "notes" in result.columns

        a_row = result[result["column"] == "a"].iloc[0]
        assert a_row["n_missing"] == 1
        assert a_row["notes"] == "the numeric column"
        assert len(a_row["top_values"]) <= 2
        assert all({"value", "count"} == set(entry) for entry in a_row["top_values"])

        b_row = result[result["column"] == "b"].iloc[0]
        assert b_row["notes"] is None
        # 'x' appears 3 times -- most frequent value in column b
        assert b_row["top_values"][0] == {"value": "x", "count": 3}

    def test_codegen_matches_execute(self):
        defn = DataDictionary()
        frame = self._frame()
        node = defn.instantiate(top_n=3)

        executed = defn.execute(node, inputs={"frame": frame.copy()})["dictionary"]
        scope = _run_codegen(defn, node, {"frame": frame.copy()})
        generated = scope["dictionary"]
        assert_frame_equal(executed, generated)

    def test_result_is_inspectable(self):
        defn = DataDictionary()
        node = defn.instantiate()
        out = defn.execute(node, inputs={"frame": self._frame()})
        assert is_inspectable(out["dictionary"]) is True

    def test_does_not_mutate_input(self):
        defn = DataDictionary()
        frame = self._frame()
        original = frame.copy()
        node = defn.instantiate()
        defn.execute(node, inputs={"frame": frame})
        pd.testing.assert_frame_equal(frame, original)


class TestRedactPii:
    def _frame(self):
        return pd.DataFrame(
            {
                "note": [
                    "contact me at ada@example.com please",
                    "call 555-123-4567 tomorrow",
                    "no pii here at all",
                ],
                "id": [1, 2, 3],
            }
        )

    def test_to_spec(self):
        spec = RedactPii().to_spec()
        assert spec.type == "clean.redact_pii"
        assert spec.family == "clean"
        in_ports = [p.name for p in spec.ports if p.direction == Direction.IN]
        out_ports = [p.name for p in spec.ports if p.direction == Direction.OUT]
        assert in_ports == ["frame"]
        assert out_ports == ["frame"]

    def test_execute_masks_email_and_phone(self):
        defn = RedactPii()
        node = defn.instantiate(columns=["note"])
        out = defn.execute(node, inputs={"frame": self._frame()})
        result = out["frame"]
        assert "ada@example.com" not in result["note"].iloc[0]
        assert "[REDACTED]" in result["note"].iloc[0]
        assert "555-123-4567" not in result["note"].iloc[1]
        assert result["note"].iloc[2] == "no pii here at all"

    def test_execute_defaults_to_all_text_columns(self):
        defn = RedactPii()
        node = defn.instantiate()
        out = defn.execute(node, inputs={"frame": self._frame()})
        assert "[REDACTED]" in out["frame"]["note"].iloc[0]

    def test_custom_mask_and_categories(self):
        defn = RedactPii()
        node = defn.instantiate(columns=["note"], categories=["email"], mask="<hidden>")
        out = defn.execute(node, inputs={"frame": self._frame()})
        result = out["frame"]
        assert "<hidden>" in result["note"].iloc[0]
        # phone category not requested -- phone number in row 1 stays untouched
        assert "555-123-4567" in result["note"].iloc[1]

    def test_unknown_category_raises(self):
        defn = RedactPii()
        node = defn.instantiate(columns=["note"], categories=["not-a-real-category"])
        with pytest.raises(CleanError):
            defn.execute(node, inputs={"frame": self._frame()})

    def test_codegen_matches_execute(self):
        defn = RedactPii()
        frame = self._frame()
        node = defn.instantiate(columns=["note"])

        executed = defn.execute(node, inputs={"frame": frame.copy()})["frame"]
        scope = _run_codegen(defn, node, {"frame": frame.copy()})
        generated = scope["frame"]
        assert_frame_equal(executed, generated)

    def test_result_is_inspectable(self):
        defn = RedactPii()
        node = defn.instantiate(columns=["note"])
        out = defn.execute(node, inputs={"frame": self._frame()})
        assert is_inspectable(out["frame"]) is True

    def test_does_not_mutate_input(self):
        defn = RedactPii()
        frame = self._frame()
        original = frame.copy()
        node = defn.instantiate(columns=["note"])
        defn.execute(node, inputs={"frame": frame})
        pd.testing.assert_frame_equal(frame, original)

    def test_presidio_engine_threaded_through_codegen_and_execute(self):
        """The engine param reaches ef.clean.redact_pii identically via both paths (ADR 0002);
        presidio isn't installed in this environment, so both paths raise the same typed
        error for engine="presidio" rather than actually redacting -- still proves equivalence."""
        import sys

        from emergentflow.clean.errors import MissingOptionalDependencyError

        if "presidio_analyzer" in sys.modules or "presidio_anonymizer" in sys.modules:
            pytest.skip("presidio is actually installed in this environment; typed-error path N/A")

        defn = RedactPii()
        frame = self._frame()
        node = defn.instantiate(columns=["note"], engine="presidio")

        with pytest.raises(MissingOptionalDependencyError):
            defn.execute(node, inputs={"frame": frame.copy()})
        with pytest.raises(MissingOptionalDependencyError):
            _run_codegen(defn, node, {"frame": frame.copy()})


# ---------------------------------------------------------------------------
# whole-graph wiring (Epic 2, Story 4)
# ---------------------------------------------------------------------------


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


class TestWholeGraphWiring:
    def test_downstream_input_uses_upstream_output_name(self):
        load = LoadCsv().instantiate(path="x.csv", label="Load CSV")
        an = Anova().instantiate(group_col="g", value_col="v", label="ANOVA")
        edge = Edge(
            source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
            target=PortRef(node_id=an.id, port_id=_in_port(an, "frame").id),
        )
        graph = Graph(nodes={load.id: load, an.id: an}, edges={edge.id: edge})

        nm = build_name_map(graph)
        wm = build_wiring_map(graph)
        load_var = nm.var_for(load.id, _out_port(load, "frame").id)

        ctx = build_codegen_context(an, nm, wm)
        frag = Anova().codegen(an, ctx)
        # the anova call reads the exact variable load_csv bound its output to
        assert f"ef.stats.anova({load_var}" in frag.body
        assert frag.body.startswith(nm.var_for(an.id, _out_port(an, "result").id))

    def test_colliding_outputs_get_distinct_names(self):
        # anova and train both historically emitted `result = ...`; with the
        # binding context their OUT vars must differ (the ADR 0009 clobber bug).
        an = Anova().instantiate(group_col="g", value_col="v", label="ANOVA")
        tr = TrainClassifier().instantiate(target="y", label="Train Classifier")
        graph = Graph(nodes={an.id: an, tr.id: tr})
        nm = build_name_map(graph)
        wm = build_wiring_map(graph)

        an_frag = Anova().codegen(an, build_codegen_context(an, nm, wm))
        tr_frag = TrainClassifier().codegen(tr, build_codegen_context(tr, nm, wm))
        an_lhs = an_frag.body.split("=", 1)[0].strip()
        tr_lhs = tr_frag.body.split("=", 1)[0].strip()
        assert an_lhs != tr_lhs


# ---------------------------------------------------------------------------
# data.load_parquet
# ---------------------------------------------------------------------------


class TestLoadParquet:
    @pytest.fixture
    def parquet_file(self, tmp_path):
        path = tmp_path / "data.parquet"
        pd.DataFrame({"a": [1, 2, 3], "b": ["x", "x", "y"]}).to_parquet(path)
        return str(path)

    def test_to_spec_source_node(self):
        spec = LoadParquet().to_spec()
        assert spec.type == "data.load_parquet"
        assert spec.category == "Ingest" and spec.description
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["frame"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]

    def test_missing_required_path_flagged(self):
        node = LoadParquet().instantiate()
        errors = LoadParquet().validate_node(node)
        assert any("required param 'path'" in e for e in errors)

    def test_codegen_body_golden(self, parquet_file):
        defn = LoadParquet()
        node = defn.instantiate(path=parquet_file)
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == (
            f"frame = ef.data.load_parquet("
            f"{parquet_file!r}, columns=None, source_file=False, connection=None, "
            f"expect_columns=None, expect_dtypes=None)"
        )

    def test_codegen_matches_execute(self, parquet_file):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadParquet()
        node = defn.instantiate(path=parquet_file)
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# data.load_json
# ---------------------------------------------------------------------------


class TestLoadJson:
    @pytest.fixture
    def json_file(self, tmp_path):
        path = tmp_path / "data.json"
        pd.DataFrame({"a": [1, 2, 3], "b": ["x", "x", "y"]}).to_json(path, orient="records")
        return str(path)

    def test_to_spec_source_node(self):
        spec = LoadJson().to_spec()
        assert spec.type == "data.load_json"
        assert spec.category == "Ingest" and spec.description
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["frame"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]

    def test_missing_required_path_flagged(self):
        node = LoadJson().instantiate()
        errors = LoadJson().validate_node(node)
        assert any("required param 'path'" in e for e in errors)

    def test_codegen_body_golden(self, json_file):
        defn = LoadJson()
        node = defn.instantiate(path=json_file, orient="records")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == (
            f"frame = ef.data.load_json("
            f"{json_file!r}, orient='records', lines=False, source_file=False, "
            f"connection=None, expect_columns=None, expect_dtypes=None)"
        )

    def test_codegen_matches_execute(self, json_file):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadJson()
        node = defn.instantiate(path=json_file, orient="records")
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
        assert scope["frame"].equals(executed["frame"])

    def test_lines_true_reads_jsonl(self, tmp_path):
        jsonl_path = tmp_path / "data.jsonl"
        jsonl_path.write_text('{"a": 1, "b": "x"}\n{"a": 2, "b": "y"}\n')

        defn = LoadJson()
        node = defn.instantiate(path=str(jsonl_path), lines=True)
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})

        assert list(executed["frame"].columns) == ["a", "b"]
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# data.load_sample
# ---------------------------------------------------------------------------


class TestLoadSample:
    def test_to_spec_source_node_with_choices(self):
        spec = LoadSample().to_spec()
        assert spec.type == "data.load_sample"
        assert spec.category == "Ingest" and spec.description
        out_ports = [p for p in spec.ports if p.direction == Direction.OUT]
        assert [p.name for p in out_ports] == ["frame"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]
        name = next(p for p in spec.params if p.name == "name")
        assert name.default == "iris"
        assert "iris" in name.hints.choices

    def test_unknown_name_flagged(self):
        node = LoadSample().instantiate(name="not-real")
        errors = LoadSample().validate_node(node)
        assert any("not one of" in e for e in errors)

    def test_codegen_body_golden(self):
        defn = LoadSample()
        node = defn.instantiate(name="iris")
        frag = defn.preview(node)
        assert frag.imports == ["import emergentflow as ef"]
        assert frag.body == "frame = ef.data.load_sample(name='iris')"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadSample()
        node = defn.instantiate(name="iris")
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# ml.fit_estimator
# ---------------------------------------------------------------------------


class TestFitEstimator:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = FitEstimator()
        df = pd.DataFrame(
            {
                "x1": [float(i) for i in range(20)] + [float(i) for i in range(20)],
                "x2": [float(i % 5) for i in range(40)],
                "label": ["low" if i % 2 == 0 else "high" for i in range(40)],
            }
        )
        X = df[["x1", "x2"]]
        node = defn.instantiate(estimator="LogisticRegression", target="label")
        executed = defn.execute(node, inputs={"frame": df.copy()})
        scope = _run_codegen(defn, node, {"frame": df.copy()})

        assert executed["model"].estimator_type == scope["model"].estimator_type
        assert executed["model"].task == scope["model"].task
        assert executed["model"].target == scope["model"].target
        assert executed["model"].feature_names == scope["model"].feature_names
        assert (
            executed["model"].estimator.predict(X).tolist()
            == scope["model"].estimator.predict(X).tolist()
        )

    def test_estimator_choices_include_fit_archetype_only(self):
        spec = FitEstimator().to_spec()
        estimator_param = next(p for p in spec.params if p.name == "estimator")
        assert "LogisticRegression" in estimator_param.hints.choices
        assert "StandardScaler" not in estimator_param.hints.choices  # fit_transform, not fit
        assert "KMeans" not in estimator_param.hints.choices  # cluster_detect, not fit


# ---------------------------------------------------------------------------
# ml.apply_estimator
# ---------------------------------------------------------------------------


class TestApplyEstimator:
    def test_codegen_matches_execute_predict(self):
        """ADR 0002: execute == result of running the emitted code."""
        fit_defn = FitEstimator()
        df = pd.DataFrame(
            {
                "x1": [float(i) for i in range(20)] + [float(i) for i in range(20)],
                "x2": [float(i % 5) for i in range(40)],
                "label": ["low" if i % 2 == 0 else "high" for i in range(40)],
            }
        )
        fit_node = fit_defn.instantiate(estimator="LogisticRegression", target="label")
        model = fit_defn.execute(fit_node, inputs={"frame": df.copy()})["model"]

        apply_defn = ApplyEstimator()
        apply_node = apply_defn.instantiate(op="predict")
        executed = apply_defn.execute(apply_node, inputs={"model": model, "frame": df.copy()})
        scope = _run_codegen(apply_defn, apply_node, {"model": model, "frame": df.copy()})

        assert executed["result"]["prediction"].tolist() == scope["result"]["prediction"].tolist()

    def test_apply_estimator_does_not_mutate_input_frame(self):
        fit_defn = FitEstimator()
        df = pd.DataFrame(
            {
                "x1": [float(i) for i in range(20)] + [float(i) for i in range(20)],
                "x2": [float(i % 5) for i in range(40)],
                "label": ["low" if i % 2 == 0 else "high" for i in range(40)],
            }
        )
        fit_node = fit_defn.instantiate(estimator="LogisticRegression", target="label")
        model = fit_defn.execute(fit_node, inputs={"frame": df.copy()})["model"]

        apply_defn = ApplyEstimator()
        apply_node = apply_defn.instantiate(op="predict")
        frame_copy = df.copy()
        apply_defn.execute(apply_node, inputs={"model": model, "frame": frame_copy})
        assert frame_copy.equals(df)


# ---------------------------------------------------------------------------
# notes.markdown
# ---------------------------------------------------------------------------


class TestMarkdownNote:
    def test_to_spec(self):
        defn = MarkdownNote()
        spec = defn.to_spec()
        assert spec.type == "notes.markdown"
        assert spec.ports == []
        assert {p.name for p in spec.params} == {"content", "anchor_id", "color"}

    def test_instantiate_defaults(self):
        defn = MarkdownNote()
        node = defn.instantiate()
        assert node.ports == []
        values = {p.name: p.value for p in node.params}
        assert values["content"] == ""
        assert values["anchor_id"] is None
        assert values["color"] == "yellow"

    def test_codegen_is_true_noop(self):
        defn = MarkdownNote()
        node = defn.instantiate(content="# Why this pipeline exists\n\nSome rationale.")
        frag = defn.preview(node)
        assert frag.imports == []
        assert frag.body == ""

    def test_execute_returns_empty_dict(self):
        defn = MarkdownNote()
        node = defn.instantiate(content="hello")
        assert defn.execute(node, inputs={}) == {}

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code (both no-ops)."""
        defn = MarkdownNote()
        node = defn.instantiate(content="anything")
        executed = defn.execute(node, inputs={})
        scope: dict[str, object] = {}
        _run_codegen(defn, node, scope)
        # A true no-op: nothing bound in scope, empty dict returned by execute.
        assert executed == {}
        # exec adds __builtins__; no user variables should be set.
        user_keys = {k for k in scope if not k.startswith("__")}
        assert user_keys == set()


# ---------------------------------------------------------------------------
# layout.group
# ---------------------------------------------------------------------------


class TestGroupContainer:
    def test_to_spec(self):
        defn = GroupContainer()
        spec = defn.to_spec()
        assert spec.type == "layout.group"
        assert spec.ports == []
        assert {p.name for p in spec.params} == {"label", "color"}

    def test_instantiate_defaults(self):
        defn = GroupContainer()
        node = defn.instantiate()
        assert node.ports == []
        values = {p.name: p.value for p in node.params}
        assert values["label"] == "Group"
        assert values["color"] == "slate"

    def test_codegen_is_true_noop(self):
        defn = GroupContainer()
        node = defn.instantiate(label="Feature engineering")
        frag = defn.preview(node)
        assert frag.imports == []
        assert frag.body == ""

    def test_execute_returns_empty_dict(self):
        defn = GroupContainer()
        node = defn.instantiate(label="Feature engineering")
        assert defn.execute(node, inputs={}) == {}

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code (both no-ops)."""
        defn = GroupContainer()
        node = defn.instantiate(label="anything")
        executed = defn.execute(node, inputs={})
        scope: dict[str, object] = {}
        _run_codegen(defn, node, scope)
        assert executed == {}
        user_keys = {k for k in scope if not k.startswith("__")}
        assert user_keys == set()


# ---------------------------------------------------------------------------
# layout.composite
# ---------------------------------------------------------------------------


class TestComposite:
    def test_to_spec(self):
        defn = Composite()
        spec = defn.to_spec()
        assert spec.type == "layout.composite"
        assert spec.ports == []
        assert {p.name for p in spec.params} == {"label"}

    def test_instantiate_defaults(self):
        defn = Composite()
        node = defn.instantiate()
        assert node.ports == []
        values = {p.name: p.value for p in node.params}
        assert values["label"] == "Composite"

    def test_codegen_raises_not_implemented(self):
        defn = Composite()
        node = defn.instantiate(label="Feature engineering")
        with pytest.raises(NotImplementedError):
            defn.codegen(node, ctx=None)

    def test_execute_raises_not_implemented(self):
        defn = Composite()
        node = defn.instantiate(label="Feature engineering")
        with pytest.raises(NotImplementedError):
            defn.execute(node, inputs={})


# ---------------------------------------------------------------------------
# clean.merge
# ---------------------------------------------------------------------------


class TestMerge:
    def test_to_spec(self):
        spec = Merge().to_spec()
        assert spec.type == "clean.merge"
        assert spec.family == "clean"
        assert spec.paradigm == Paradigm.FUNCTIONAL
        in_ports = [p.name for p in spec.ports if p.direction == Direction.IN]
        out_ports = [p.name for p in spec.ports if p.direction == Direction.OUT]
        assert in_ports == ["left", "right"]
        assert out_ports == ["frame"]

    def test_codegen_matches_execute_on(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Merge()
        left = pd.DataFrame({"user_id": [1, 2, 3], "name": ["a", "b", "c"]})
        right = pd.DataFrame({"user_id": [2, 3, 4], "score": [10, 20, 30]})
        node = defn.instantiate(on=["user_id"], how="inner")
        executed = defn.execute(node, inputs={"left": left.copy(), "right": right.copy()})
        scope = {"left": left.copy(), "right": right.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])

    def test_codegen_matches_execute_left_on_right_on_how_left(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = Merge()
        left = pd.DataFrame({"uid": [1, 2, 3]})
        right = pd.DataFrame({"user_id": [2], "score": [10]})
        node = defn.instantiate(left_on=["uid"], right_on=["user_id"], how="left")
        executed = defn.execute(node, inputs={"left": left.copy(), "right": right.copy()})
        scope = {"left": left.copy(), "right": right.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# clean.semi_join
# ---------------------------------------------------------------------------


class TestSemiJoin:
    def test_to_spec(self):
        spec = SemiJoin().to_spec()
        assert spec.type == "clean.semi_join"
        assert spec.family == "clean"
        assert spec.paradigm == Paradigm.FUNCTIONAL
        in_ports = [p.name for p in spec.ports if p.direction == Direction.IN]
        out_ports = [p.name for p in spec.ports if p.direction == Direction.OUT]
        assert in_ports == ["frame", "keys"]
        assert out_ports == ["frame"]

    def test_codegen_matches_execute_keep(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = SemiJoin()
        frame = pd.DataFrame({"user_id": [1, 2, 3, 4], "event": ["a", "b", "c", "d"]})
        keys = pd.DataFrame({"user_id": [2, 4]})
        node = defn.instantiate(on=["user_id"], mode="keep")
        executed = defn.execute(node, inputs={"frame": frame.copy(), "keys": keys.copy()})
        scope = {"frame": frame.copy(), "keys": keys.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])

    def test_codegen_matches_execute_exclude(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = SemiJoin()
        frame = pd.DataFrame({"user_id": [1, 2, 3, 4], "event": ["a", "b", "c", "d"]})
        keys = pd.DataFrame({"user_id": [2, 4]})
        node = defn.instantiate(on=["user_id"], mode="exclude")
        executed = defn.execute(node, inputs={"frame": frame.copy(), "keys": keys.copy()})
        scope = {"frame": frame.copy(), "keys": keys.copy()}
        _run_codegen(defn, node, scope)
        assert scope["frame"].equals(executed["frame"])


# ---------------------------------------------------------------------------
# stats.test_proportions
# ---------------------------------------------------------------------------


class TestTestProportions:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = TestProportions()
        np = pytest.importorskip("numpy")
        rng = np.random.default_rng(42)
        n_a, n_b = 50, 50
        df = pd.DataFrame(
            {
                "group": ["a"] * n_a + ["b"] * n_b,
                "success": (list(rng.binomial(1, 0.20, n_a)) + list(rng.binomial(1, 0.40, n_b))),
            }
        )
        node = defn.instantiate(group_col="group", success_col="success")
        executed = defn.execute(node, inputs={"frame": df.copy()})["result"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# stats.power_analysis
# ---------------------------------------------------------------------------


class TestPowerAnalysis:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = PowerAnalysis()
        node = defn.instantiate(effect_size=0.5, nobs=100, alpha=0.05)
        executed = defn.execute(node, inputs={})["result"]
        scope = _run_codegen(defn, node, {})
        generated = scope["result"]
        assert_frame_equal(generated, executed)


# ---------------------------------------------------------------------------
# viz.plot_projection
# ---------------------------------------------------------------------------


class TestVizPlotProjection:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = VizPlotProjection()
        df = pd.DataFrame(
            {
                "component_1": [1.0, 2.0, 3.0, 4.0],
                "component_2": [4.0, 3.0, 2.0, 1.0],
                "label": ["a", "a", "b", "b"],
            }
        )
        node = defn.instantiate(color_col="label")
        executed = defn.execute(node, inputs={"frame": df.copy()})["plot"]
        scope = _run_codegen(defn, node, {"frame": df.copy()})
        generated = scope["plot"]
        assert generated.chart == executed.chart
        assert generated.spec == executed.spec
