"""Tests for the reference node definitions (colonymind.nodes.examples).

Covers contract conformance for both reference nodes and the ADR-0002 invariant
at node granularity: for a given IR node, ``execute`` must produce the same
result as running the code emitted by ``codegen``.
"""

import csv

import pytest

from colonymind.ir.common import Direction, Paradigm
from colonymind.ir.graph import Graph
from colonymind.nodes.examples import ImputeMissing, LoadCsv
from colonymind.nodes.examples.impute import impute_missing


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "data.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["a", "b"])
        writer.writerow(["1", "x"])
        writer.writerow(["", "x"])
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
        assert [p.name for p in out_ports] == ["table"]
        assert not [p for p in spec.ports if p.direction == Direction.IN]

    def test_instantiate_and_validate(self):
        node = LoadCsv().instantiate(path="x.csv")
        assert LoadCsv().validate_node(node) == []

    def test_missing_required_path_flagged(self):
        node = LoadCsv().instantiate()  # path unset
        errors = LoadCsv().validate_node(node)
        assert any("required param 'path'" in e for e in errors)

    def test_execute_reads_rows(self, csv_file):
        node = LoadCsv().instantiate(path=csv_file)
        out = LoadCsv().execute(node, inputs={})
        assert out["table"] == [
            {"a": "1", "b": "x"},
            {"a": "", "b": "x"},
            {"a": "3", "b": "y"},
        ]

    def test_codegen_matches_execute(self, csv_file):
        """ADR 0002: execute == result of running the emitted code."""
        defn = LoadCsv()
        node = defn.instantiate(path=csv_file)
        executed = defn.execute(node, inputs={})
        scope = _run_codegen(defn, node, {})
        assert scope["table"] == executed["table"]

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
        # OUT ``table`` namespaces are independent, and instantiate() must still
        # mint a graph-valid node (distinct port ids).
        node = ImputeMissing().instantiate()
        by_dir = {p.direction: p for p in node.ports}
        assert by_dir[Direction.IN].name == by_dir[Direction.OUT].name == "table"
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
        table = [{"a": "1"}, {"a": ""}, {"a": "3"}]
        node = ImputeMissing().instantiate(strategy="mean")
        out = ImputeMissing().execute(node, inputs={"table": table})
        assert [r["a"] for r in out["table"]] == ["1", 2.0, "3"]

    def test_execute_most_frequent(self):
        table = [{"c": "x"}, {"c": ""}, {"c": "x"}]
        node = ImputeMissing().instantiate(strategy="most_frequent")
        out = ImputeMissing().execute(node, inputs={"table": table})
        assert [r["c"] for r in out["table"]] == ["x", "x", "x"]

    def test_helper_median(self):
        assert impute_missing([{"a": "1"}, {"a": "3"}, {"a": ""}, {"a": "5"}],
                              strategy="median")[2]["a"] == 3.0

    def test_columns_subset(self):
        node = ImputeMissing().instantiate(strategy="most_frequent", columns=["a"])
        out = ImputeMissing().execute(node, inputs={"table": [{"a": "1"}, {"a": ""},
                                                              {"b": ""}]})
        # only 'a' touched; 'b' rows untouched
        assert out["table"][1]["a"] == "1"

    def test_codegen_matches_execute(self):
        """ADR 0002: execute == result of running the emitted code."""
        defn = ImputeMissing()
        table = [{"a": "1"}, {"a": ""}, {"a": "3"}]
        node = defn.instantiate(strategy="mean")
        executed = defn.execute(node, inputs={"table": table})
        scope = {"table": [dict(r) for r in table]}
        _run_codegen(defn, node, scope)
        assert scope["table"] == executed["table"]
