"""Tests for emergentflow.codegen.mermaid — pure Mermaid flowchart rendering (issue #169)."""

from __future__ import annotations

import pytest

from emergentflow.api import is_inspectable
from emergentflow.codegen.mermaid import _mermaid_label, to_mermaid
from emergentflow.ir import Direction, Edge, Graph, Node, Port, PortRef
from emergentflow.ir.params import Param

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _node(
    nid: str,
    type_: str = "test.node",
    label: str | None = None,
    *,
    in_name: str | None = "df",
    out_name: str | None = "df",
    group_id: str | None = None,
    subgraph: Graph | None = None,
    params: list[Param] | None = None,
) -> Node:
    ports: list[Port] = []
    if in_name is not None:
        ports.append(Port(id=f"{nid}-in", name=in_name, direction=Direction.IN))
    if out_name is not None:
        ports.append(Port(id=f"{nid}-out", name=out_name, direction=Direction.OUT))
    return Node(
        id=nid,
        type=type_,
        label=label,
        ports=ports,
        group_id=group_id,
        subgraph=subgraph,
        params=params or [],
    )


def _edge(src: str, tgt: str) -> Edge:
    return Edge(
        id=f"{src}->{tgt}",
        source=PortRef(node_id=src, port_id=f"{src}-out"),
        target=PortRef(node_id=tgt, port_id=f"{tgt}-in"),
    )


def _graph(nodes: list[Node], edges: list[Edge] | None = None) -> Graph:
    return Graph(nodes={n.id: n for n in nodes}, edges={e.id: e for e in (edges or [])})


def _chain() -> Graph:
    a = _node("a", "data.load_csv", "Load", in_name=None, out_name="frame")
    b = _node("b", "clean.impute_missing", "Impute")
    c = _node("c", "stats.anova", "Test", out_name=None, in_name="x")
    return _graph([a, b, c], [_edge("a", "b"), _edge("b", "c")])


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------


def test_mermaid_label_escapes_hostile_characters() -> None:
    out = _mermaid_label('a"b[c]d|e<f>g#h&i`j{k}\nl')
    assert out == "a#quot;b#91;c#93;d#124;e#lt;f#gt;g#35;h#amp;i#96;j#123;k#125;<br/>l"
    stripped = out.replace("<br/>", "")
    for raw in ('"', "[", "]", "|", "<", ">"):
        assert raw not in stripped


def test_mermaid_label_no_double_escape() -> None:
    assert _mermaid_label("#quot;") == "#35;quot;"


def test_hostile_label_node_line() -> None:
    g = _graph([_node("a", "data.load_csv", 'Load "CSV" [v2] | <x>')])
    out = to_mermaid(g)
    assert "Load #quot;CSV#quot; #91;v2#93; #124; #lt;x#gt;" in out


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_linear_chain_output_exact() -> None:
    expected = (
        "flowchart LR\n"
        '    n_a["Load<br/><small>data.load_csv</small>"]\n'
        '    n_b["Impute<br/><small>clean.impute_missing</small>"]\n'
        '    n_c["Test<br/><small>stats.anova</small>"]\n'
        "    n_a -->|frame→df| n_b\n"
        "    n_b -->|df→x| n_c\n"
        "    classDef fam_clean stroke:#14b8a6,stroke-width:2px\n"
        "    class n_b fam_clean\n"
        "    classDef fam_data stroke:#3b82f6,stroke-width:2px\n"
        "    class n_a fam_data\n"
        "    classDef fam_stats stroke:#a78bfa,stroke-width:2px\n"
        "    class n_c fam_stats\n"
    )
    assert to_mermaid(_chain()) == expected


def test_deterministic_regardless_of_insertion_order() -> None:
    g = _chain()
    reversed_graph = Graph(
        nodes=dict(reversed(list(g.nodes.items()))),
        edges=dict(reversed(list(g.edges.items()))),
    )
    assert to_mermaid(g) == to_mermaid(reversed_graph)


def test_port_label_same_name_vs_different() -> None:
    a = _node("a", "data.load_csv", "A", in_name=None, out_name="df")
    b = _node("b", "clean.impute_missing", "B", in_name="df", out_name="out")
    c = _node("c", "stats.anova", "C", in_name="x", out_name=None)
    out = to_mermaid(_graph([a, b, c], [_edge("a", "b"), _edge("b", "c")]))
    assert "n_a -->|df| n_b" in out
    assert "n_b -->|out→x| n_c" in out


def test_show_ports_false_and_show_types_false() -> None:
    out = to_mermaid(_chain(), show_ports=False, show_types=False)
    assert '    n_a["Load"]' in out
    assert "<small>" not in out
    assert "    n_a --> n_b" in out
    assert "|" not in out


def test_direction_tb() -> None:
    assert to_mermaid(_chain(), direction="TB").startswith("flowchart TB\n")


def test_invalid_direction_raises() -> None:
    with pytest.raises(ValueError):
        to_mermaid(_chain(), direction="RL")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        to_mermaid(_chain(), max_nodes=0)


def test_presentation_nodes_omitted_by_default_and_included_on_request() -> None:
    a = _node("a", "data.load_csv", "Load", in_name=None, out_name="df")
    note = _node("note", "notes.markdown", "My note", in_name=None, out_name=None)
    g = _graph([a, note])
    assert "My note" not in to_mermaid(g)
    assert 'n_note["My note' in to_mermaid(g, include_notes=True)


# ---------------------------------------------------------------------------
# Groups and containers
# ---------------------------------------------------------------------------


def _grouped() -> Graph:
    grp = _node("grp", "layout.group", "Prep", in_name=None, out_name=None)
    a = _node("a", "data.load_csv", "Load", in_name=None, out_name="df")
    b = _node("b", "clean.impute_missing", "Impute", group_id="grp")
    c = _node("c", "stats.anova", "Test", out_name=None, group_id="grp")
    return _graph([grp, a, b, c], [_edge("a", "b"), _edge("b", "c")])


def test_group_renders_subgraph_block() -> None:
    out = to_mermaid(_grouped())
    lines = out.splitlines()
    assert '    subgraph g_grp["Prep"]' in lines
    start = lines.index('    subgraph g_grp["Prep"]')
    assert lines[start + 1].startswith('        n_b["Impute')
    assert lines[start + 2].startswith('        n_c["Test')
    assert lines[start + 3] == "    end"
    assert "n_grp" not in out


def test_groups_false_flattens() -> None:
    out = to_mermaid(_grouped(), groups=False)
    assert "subgraph" not in out
    assert '    n_b["Impute' in out


def test_container_subgraph_nested_and_deeper_flattened() -> None:
    deep_inner = _graph([_node("z", "nn.linear", "Deep")])
    lin = _node("lin", "nn.linear", "Lin", in_name=None, out_name="out")
    deeper = _node("deeper", "nn.module", "Deeper", subgraph=deep_inner)
    relu = _node("relu", "nn.relu", "Relu")
    inner = _graph([lin, deeper, relu], [_edge("lin", "relu")])
    mod = _node("mod", "nn.module", "Model", subgraph=inner)
    src = _node("src", "data.load_csv", "Src", in_name=None, out_name="df")
    out = to_mermaid(_graph([src, mod], [_edge("src", "mod")]))
    lines = out.splitlines()
    assert '    subgraph n_mod["Model<br/><small>nn.module</small>"]' in lines
    assert "        n_lin" in out
    assert "        %% flattened: nested subgraph of Deeper (1 nodes) not shown" in lines
    assert '        n_deeper["Deeper' in out
    assert "n_z" not in out
    assert "    n_src -->|df| n_mod" in lines
    assert any(line.startswith("    n_lin -->") or "n_lin -->" in line for line in lines)


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------


def test_highlight_classdef_and_unknown_id_ignored() -> None:
    out = to_mermaid(_chain(), highlight=["b", "does-not-exist"])
    assert "    classDef highlight stroke:#ef4444,stroke-width:4px" in out
    assert "    class n_b highlight" in out
    assert "does-not-exist" not in out
    assert "highlight" not in to_mermaid(_chain(), highlight=["nope"])


def test_family_classdef_uses_palette() -> None:
    out = to_mermaid(_graph([_node("a", "data.load_csv", "L")]))
    assert "classDef fam_data stroke:#3b82f6" in out


# ---------------------------------------------------------------------------
# Size guard
# ---------------------------------------------------------------------------


def test_size_guard_truncates_with_comment() -> None:
    nodes = [_node(f"n{i:02d}", "data.load_csv", f"N{i}") for i in range(10)]
    edges = [_edge(f"n{i:02d}", f"n{i + 1:02d}") for i in range(9)]
    out = to_mermaid(_graph(nodes, edges), max_nodes=4)
    lines = out.splitlines()
    assert lines[1].startswith("    %% truncated:")
    assert "6 of 10 nodes" in lines[1]
    assert sum(1 for line in lines if '["' in line) == 4
    assert "n_n04" not in out


def test_size_guard_collapses_groups() -> None:
    grp = _node("grp", "layout.group", "Big", in_name=None, out_name=None)
    members = [_node(f"m{i}", "clean.impute_missing", f"M{i}", group_id="grp") for i in range(6)]
    outside = _node("out", "data.load_csv", "Out", in_name=None, out_name="df")
    edges = [_edge("out", "m0")]
    out = to_mermaid(_graph([grp, outside, *members], edges), max_nodes=3)
    assert "subgraph" not in out
    group_lines = [line for line in out.splitlines() if line.strip().startswith("g_")]
    assert len(group_lines) == 1
    assert "6 nodes" in group_lines[0]
    assert "n_out --> g_grp" in out


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_cycle_does_not_raise() -> None:
    a = _node("a", "data.load_csv", "A")
    b = _node("b", "clean.impute_missing", "B")
    out = to_mermaid(_graph([a, b], [_edge("a", "b"), _edge("b", "a")]))
    assert "n_a -->" in out
    assert "n_b -->" in out


def test_id_collision_disambiguated() -> None:
    g = _graph([_node("a-b", "data.load_csv", "One"), _node("a_b", "data.load_csv", "Two")])
    out = to_mermaid(g)
    assert 'n_a_b["One' in out
    assert 'n_a_b_2["Two' in out


def test_is_inspectable() -> None:
    out = to_mermaid(_chain())
    assert isinstance(out, str)
    assert is_inspectable(out)


def test_ef_to_mermaid_is_lazy_entry_point() -> None:
    import emergentflow as ef
    from emergentflow.codegen.mermaid import to_mermaid as direct

    assert "to_mermaid" in ef.__all__
    assert ef.to_mermaid is direct
