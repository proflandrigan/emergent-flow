"""Tests for emergentflow.codegen.naming — string-level slug and identifier
helpers, plus smoke tests for the whole-graph `NameMap` / `build_name_map`
(Epic 2, Story 3). The exhaustive naming corpus comes in a later task."""

from __future__ import annotations

import keyword

import pytest

from emergentflow.api import is_inspectable
from emergentflow.codegen.naming import (
    NameMap,
    _sanitize_identifier,
    _slugify,
    build_name_map,
)
from emergentflow.ir import Direction, Graph, Node, Port

# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


def test_slugify_lowercases_and_joins_words() -> None:
    assert _slugify("Load CSV") == "load_csv"


def test_slugify_collapses_runs_of_separators() -> None:
    assert _slugify("  Train   Classifier  ") == "train_classifier"


def test_slugify_transliterates_unicode() -> None:
    assert _slugify("café") == "cafe"


def test_slugify_drops_text_with_no_ascii_survivors() -> None:
    assert _slugify("数据") == ""


def test_slugify_empty_string() -> None:
    assert _slugify("") == ""


# ---------------------------------------------------------------------------
# _sanitize_identifier
# ---------------------------------------------------------------------------


def test_sanitize_identifier_escapes_keyword() -> None:
    assert _sanitize_identifier("class") == "class_"


def test_sanitize_identifier_escapes_builtin() -> None:
    assert _sanitize_identifier("id") == "id_"


def test_sanitize_identifier_prefixes_leading_digit() -> None:
    assert _sanitize_identifier("3d_plot") == "_3d_plot"


def test_sanitize_identifier_empty_string() -> None:
    assert _sanitize_identifier("") == ""


def test_sanitize_identifier_passes_through_ordinary_slug() -> None:
    assert _sanitize_identifier("load_csv") == "load_csv"


# ---------------------------------------------------------------------------
# build_name_map / NameMap — smoke tests (exhaustive corpus is a later task)
# ---------------------------------------------------------------------------


def _out_node(label: str, out_names: list[str]) -> Node:
    ports = [Port(name=name, direction=Direction.OUT) for name in out_names]
    return Node(type="test.node", label=label, ports=ports)


def _out_port(node: Node, idx: int = 0) -> Port:
    return [p for p in node.ports if p.direction == Direction.OUT][idx]


def _graph(nodes: list[Node]) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={})


def test_build_name_map_always_suffixes_port_name() -> None:
    node = _out_node("Load CSV", ["frame"])
    graph = _graph([node])
    name_map = build_name_map(graph)

    assert name_map.var_for(node.id, _out_port(node).id) == "load_csv_frame"


def test_build_name_map_disambiguates_colliding_candidates() -> None:
    a = _out_node("ANOVA", ["result"])
    b = _out_node("ANOVA", ["result"])
    graph = _graph([a, b])
    name_map = build_name_map(graph)

    name_a = name_map.var_for(a.id, _out_port(a).id)
    name_b = name_map.var_for(b.id, _out_port(b).id)

    assert name_a.startswith("anova_result_")
    assert name_b.startswith("anova_result_")
    assert name_a != name_b


def test_build_name_map_result_is_inspectable() -> None:
    node = _out_node("Load CSV", ["frame"])
    graph = _graph([node])
    result = build_name_map(graph)

    assert isinstance(result, NameMap)
    assert is_inspectable(result)


def test_var_for_unknown_port_raises_key_error() -> None:
    node = _out_node("Load CSV", ["frame"])
    graph = _graph([node])
    name_map = build_name_map(graph)

    with pytest.raises(KeyError):
        name_map.var_for(node.id, "not-a-real-port-id")


# ---------------------------------------------------------------------------
# build_name_map / NameMap — exhaustive graph-level corpus (Story 3, Task 03)
# ---------------------------------------------------------------------------


def _node(label: str | None, *, type_: str = "test.node", outs: tuple[str, ...] = ("out",)) -> Node:
    ports = [Port(name=n, direction=Direction.OUT) for n in outs]
    return Node(type=type_, label=label, ports=ports)


def test_label_with_spaces_produces_expected_var() -> None:
    node = _node("Load CSV", outs=("frame",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    assert name_map.var_for(node.id, _out_port(node).id) == "load_csv_frame"


def test_duplicate_labels_disambiguate_and_resolve() -> None:
    a = _node("ANOVA", outs=("result",))
    b = _node("ANOVA", outs=("result",))
    graph = _graph([a, b])
    name_map = build_name_map(graph)

    name_a = name_map.var_for(a.id, _out_port(a).id)
    name_b = name_map.var_for(b.id, _out_port(b).id)

    assert name_a.startswith("anova_result_")
    assert name_b.startswith("anova_result_")
    assert name_a != name_b


def test_unicode_label_falls_back_to_type_derived_name() -> None:
    node = _node("数据", type_="data.load_csv", outs=("frame",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    expected = f"{_sanitize_identifier(_slugify(node.type))}_frame"
    assert expected == "data_load_csv_frame"
    assert name_map.var_for(node.id, _out_port(node).id) == expected


def test_keyword_label_escapes_base_and_stays_valid_identifier() -> None:
    node = _node("class", outs=("out",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    var = name_map.var_for(node.id, _out_port(node).id)
    assert var == "class__out"
    assert var.isidentifier()
    assert not keyword.iskeyword(var)


def test_builtin_label_escapes_base_and_stays_valid_identifier() -> None:
    node = _node("type", outs=("out",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    var = name_map.var_for(node.id, _out_port(node).id)
    assert var == "type__out"
    assert var.isidentifier()
    assert not keyword.iskeyword(var)


def test_empty_label_falls_back_to_type_derived_name() -> None:
    node = _node("", type_="data.load_csv", outs=("frame",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    var = name_map.var_for(node.id, _out_port(node).id)
    expected = f"{_sanitize_identifier(_slugify(node.type))}_frame"
    assert var == expected
    assert var.isidentifier()


def test_none_label_falls_back_to_type_derived_name() -> None:
    node = _node(None, type_="data.load_csv", outs=("frame",))
    graph = _graph([node])
    name_map = build_name_map(graph)

    var = name_map.var_for(node.id, _out_port(node).id)
    expected = f"{_sanitize_identifier(_slugify(node.type))}_frame"
    assert var == expected
    assert var.isidentifier()


def test_multi_output_node_gets_distinct_prefixed_vars() -> None:
    node = _node("Split", outs=("train", "test"))
    graph = _graph([node])
    name_map = build_name_map(graph)

    out_ports = [p for p in node.ports if p.direction == Direction.OUT]
    train_port, test_port = out_ports[0], out_ports[1]

    var_train = name_map.var_for(node.id, train_port.id)
    var_test = name_map.var_for(node.id, test_port.id)

    assert var_train == "split_train"
    assert var_test == "split_test"
    assert var_train != var_test


def test_build_name_map_is_stable_across_repeated_calls() -> None:
    a = _node("Load CSV", outs=("frame",))
    b = _node("ANOVA", outs=("result",))
    c = _node("ANOVA", outs=("result",))
    graph = _graph([a, b, c])

    first = build_name_map(graph)
    second = build_name_map(graph)
    assert first.bindings == second.bindings

    # Rebuilding the graph from the same node objects must be just as stable.
    rebuilt_graph = _graph([a, b, c])
    third = build_name_map(rebuilt_graph)
    assert first.bindings == third.bindings


def test_whole_graph_var_names_are_unique_and_valid_identifiers() -> None:
    nodes = [
        _node("Load CSV", outs=("frame",)),
        _node("ANOVA", outs=("result",)),
        _node("ANOVA", outs=("result",)),
        _node("数据", type_="data.load_csv", outs=("frame",)),
        _node("class", outs=("out",)),
        _node("type", outs=("out",)),
        _node("", type_="data.load_csv", outs=("frame",)),
        _node(None, type_="data.load_csv", outs=("frame",)),
        _node("Split", outs=("train", "test")),
        _node("NoOutputs", outs=()),
    ]
    graph = _graph(nodes)
    name_map = build_name_map(graph)

    names = [b.var_name for b in name_map.bindings]
    assert len(set(names)) == len(names)
    for name in names:
        assert name.isidentifier()
        assert not keyword.iskeyword(name)


def test_build_name_map_result_is_inspectable_for_full_corpus() -> None:
    nodes = [
        _node("Load CSV", outs=("frame",)),
        _node("ANOVA", outs=("result",)),
        _node("ANOVA", outs=("result",)),
        _node("Split", outs=("train", "test")),
    ]
    graph = _graph(nodes)
    name_map = build_name_map(graph)

    assert is_inspectable(name_map)
