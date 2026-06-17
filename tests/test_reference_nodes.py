"""Tests for the reference node definitions (colonymind.nodes.examples).

Covers contract conformance for both reference nodes and the ADR-0002 invariant
at node granularity: for a given IR node, ``execute`` must produce the same
result as running the code emitted by ``codegen``.
"""

import csv

import pandas as pd
import pytest

from colonymind.ir.common import Direction, Paradigm
from colonymind.ir.graph import Graph
from colonymind.nodes.examples import (
    Anova,
    GenerateHtmlSummary,
    ImputeMissing,
    LoadCsv,
    TrainClassifier,
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
    """exec a node's emitted fragment in *scope* and return the updated scope."""
    frag = definition.codegen(node)
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
# reports.generate_html_summary
# ---------------------------------------------------------------------------


class TestGenerateHtmlSummary:
    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code.

        ydata-profiling embeds a generation timestamp, so the HTML is not
        byte-reproducible between calls (see ``colonymind.reports``). We assert
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
