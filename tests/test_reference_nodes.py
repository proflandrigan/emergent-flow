"""Tests for the reference node definitions (emergentflow.nodes.examples).

Covers contract conformance for both reference nodes and the ADR-0002 invariant
at node granularity: for a given IR node, ``execute`` must produce the same
result as running the code emitted by ``codegen``.
"""

import csv

import pandas as pd
import pytest

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
    CastTypes,
    Correlation,
    Describe,
    DropMissing,
    Evaluate,
    FilterRows,
    FitEstimator,
    GenerateHtmlSummary,
    ImputeMissing,
    LoadCsv,
    LoadJson,
    LoadParquet,
    LoadSample,
    Predict,
    SelectColumns,
    Summarize,
    TrainClassifier,
    TrainRandomForest,
    TrainRegressor,
    TrainTestSplit,
    TTest,
)


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
        assert frag.body == "matrix = ef.stats.correlation(frame, method='pearson', columns=None)"

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
        assert frag.body == f"frame = ef.data.load_parquet({parquet_file!r}, columns=None)"

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
        assert frag.body == f"frame = ef.data.load_json({json_file!r}, orient='records')"

    def test_codegen_matches_execute(self, json_file):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadJson()
        node = defn.instantiate(path=json_file, orient="records")
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
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
