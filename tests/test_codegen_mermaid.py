"""Tests for emergentflow.codegen.mermaid — pure Mermaid flowchart rendering (issue #169)."""

from __future__ import annotations

import re

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
        '    n_a -->|"frame→df"| n_b\n'
        '    n_b -->|"df→x"| n_c\n'
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
    assert 'n_a -->|"df"| n_b' in out
    assert 'n_b -->|"out→x"| n_c' in out


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
    assert '    n_src -->|"df"| n_mod' in lines
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


def test_percent_in_label_is_escaped() -> None:
    a = _node("a", "data.load_csv", "Rate %% of 100%")
    out = to_mermaid(_graph([a], []))
    assert "%%" not in out
    assert "Rate #37;#37; of 100#37;" in out


def test_colon_in_user_text_is_escaped() -> None:
    # Mermaid's pre-parse ``encodeEntities`` strips the last ``;`` of any line matching
    # ``style.*:\S*#.*;`` (``Lifestyle:<30`` rendered as ``Lifestyle:#lt30``), so no literal
    # ``:`` from user text may reach a node, edge or subgraph line.
    a = _node("lifestyle", "data.load_csv", "Lifestyle:<30", in_name=None, out_name="style:x")
    b = _node("b", "clean.impute_missing", "Age:<30", in_name="in")
    grp = _node("g", "layout.group", "style:50%", in_name=None, out_name=None)
    m = _node("m", "clean.impute_missing", "M", group_id="g")
    out = to_mermaid(_graph([a, b, grp, m], [_edge("lifestyle", "b")]))
    lines = out.splitlines()
    assert '    n_lifestyle["Lifestyle#58;#lt;30<br/><small>data.load_csv</small>"]' in lines
    assert '    n_b["Age#58;#lt;30<br/><small>clean.impute_missing</small>"]' in lines
    assert '    n_lifestyle -->|"style#58;x→in"| n_b' in lines
    assert '    subgraph g_g["style#58;50#37;"]' in lines
    for line in lines:
        if not line.strip().startswith(("classDef ", "%%")):
            assert ":" not in line, line


def test_highlight_accepts_bare_string_id() -> None:
    a = _node("abc", "data.load_csv", "A")
    b = _node("b", "clean.impute_missing", "B")
    out = to_mermaid(_graph([a, b], [_edge("abc", "b")]), highlight="abc")  # type: ignore[arg-type]
    assert "class n_abc highlight" in out
    assert "n_b highlight" not in out and ",n_b" not in out


def test_truncation_count_does_not_treat_group_as_one_drawn_node() -> None:
    grp = _node("grp", "layout.group", "Big", in_name=None, out_name=None)
    members = [_node(f"m{i}", "clean.impute_missing", f"M{i}", group_id="grp") for i in range(6)]
    outside = _node("out", "data.load_csv", "Out", in_name=None, out_name="df")
    out = to_mermaid(_graph([grp, outside, *members], [_edge("out", "m0")]), max_nodes=3)
    assert "%% truncated: 6 of 7 nodes not drawn individually" in out


@pytest.mark.parametrize(
    "port", ["count(*)", "f(x)", "~~~", "click a call foo()", "@{ shape: rect }"]
)
def test_edge_text_is_quoted(port: str) -> None:
    # Unquoted |...| edge text breaks the Mermaid parser on (, ), ~~~, @ (PR #177 review).
    a = _node("a", "data.load_csv", "Load", in_name=None, out_name=port)
    b = _node("b", "clean.impute_missing", "Impute", in_name="df")
    out = to_mermaid(_graph([a, b], [_edge("a", "b")]))
    assert f'    n_a -->|"{_mermaid_label(port + "→df")}"| n_b' in out.splitlines()


def test_label_neutralises_direction_token() -> None:
    assert _mermaid_label("Stage: direction LR") == "Stage#58; direction#32;LR"
    assert _mermaid_label("direction\tTB") == "direction#9;TB"
    assert _mermaid_label("direction   TD x") == "direction#32;  TD x"
    assert _mermaid_label("subdirection BT") == "subdirection#32;BT"
    assert _mermaid_label("direction\ufeffRL") == "direction#65279;RL"
    # The lexer rule is case-sensitive and needs whitespace + a direction keyword.
    for safe in ("Direction TB", "direction tb", "direction", "directions LR"):
        assert _mermaid_label(safe) == safe


def test_group_and_module_titles_with_direction_token() -> None:
    grp = _node("g", "layout.group", "Stage: direction LR", in_name=None, out_name=None)
    out = to_mermaid(_graph([grp, _node("m", "data.load_csv", "M", group_id="g")]))
    assert '    subgraph g_g["Stage#58; direction#32;LR"]' in out.splitlines()

    inner = _graph([_node("l1", "nn.linear", "lin")])
    mod = _node("mod", "nn.module", "Encoder (direction TB)", subgraph=inner)
    out = to_mermaid(_graph([mod]))
    assert '    subgraph n_mod["Encoder (direction#32;TB)<br/><small>nn.module</small>"]' in (
        out.splitlines()
    )


# Mermaid's lexer applies ``.*direction\s+(TB|BT|RL|LR|TD)`` to every line, so any emitted
# line matching it (other than real direction statements) silently loses its content.
_LEXER_DIRECTION = re.compile(r"direction\s+(TB|BT|RL|LR|TD)")
_HOSTILE = "direction TB"


def _assert_no_stray_direction(out: str) -> None:
    stray = [line for line in out.splitlines() if _LEXER_DIRECTION.search(line)]
    assert stray == []


def _hostile_cases() -> dict[str, tuple[Graph, int]]:
    label = _graph([_node("a", "data.load_csv", _HOSTILE)])
    type_ = _graph([_node("a", _HOSTILE, "A")])
    port = _graph(
        [
            _node("a", "data.load_csv", "A", in_name=None, out_name=_HOSTILE),
            _node("b", "clean.impute_missing", "B"),
        ],
        [_edge("a", "b")],
    )
    inner_mod = _graph(
        [_node("mod", "nn.module", "M", subgraph=_graph([_node("l1", "nn.linear", _HOSTILE)]))]
    )
    deep = _graph([_node("x", "nn.linear", "x")])
    nested = _node("inner", "nn.module", _HOSTILE, subgraph=deep)
    flat_comment = _graph(
        [_node("mod", "nn.module", "M", subgraph=_graph([nested, _node("l2", "nn.relu", "r")]))]
    )
    grp = _node("g", "layout.group", _HOSTILE, in_name=None, out_name=None)
    members = [_node(f"m{i}", "clean.impute_missing", f"M{i}", group_id="g") for i in range(3)]
    collapsed = _graph([grp, *members, _node("o", "data.load_csv", _HOSTILE)])
    return {
        "label": (label, 0),
        "type": (type_, 0),
        "port": (port, 0),
        "inner_module": (inner_mod, 0),
        "flat_comment": (flat_comment, 0),
        "group": (collapsed, 0),
        "collapsed": (collapsed, 1),
    }


@pytest.mark.parametrize("case", list(_hostile_cases()))
def test_no_stray_direction_statement_in_any_line(case: str) -> None:
    graph, max_nodes = _hostile_cases()[case]
    kwargs = {"max_nodes": max_nodes} if max_nodes else {}
    for direction in ("LR", "TB"):
        out = to_mermaid(graph, direction=direction, **kwargs)  # type: ignore[arg-type]
        assert out.splitlines()[0] == f"flowchart {direction}"
        _assert_no_stray_direction(out)
        assert "direction#32;TB" in out


def test_flattened_comment_neutralises_direction_token() -> None:
    graph, _ = _hostile_cases()["flat_comment"]
    lines = to_mermaid(graph).splitlines()
    assert "        %% flattened: nested subgraph of direction#32;TB (1 nodes) not shown" in lines


# ---------------------------------------------------------------------------
# Canvas title precedence (the ``label`` param wins for param-titled types)
# ---------------------------------------------------------------------------


def test_canvas_renamed_group_uses_label_param() -> None:
    # Canvas shape: node.label stays "Group"; renaming only edits the ``label`` param.
    grp = _node(
        "grp",
        "layout.group",
        "Group",
        in_name=None,
        out_name=None,
        params=[Param(name="label", type_token="str", value="Preprocessing")],
    )
    members = [_node(f"m{i}", "clean.impute_missing", f"M{i}", group_id="grp") for i in range(3)]
    g = _graph([grp, *members])
    assert '    subgraph g_grp["Preprocessing"]' in to_mermaid(g).splitlines()
    collapsed = to_mermaid(g, max_nodes=1)
    assert "Preprocessing" in collapsed
    assert '"Group' not in collapsed


def test_group_without_label_param_falls_back_to_node_label() -> None:
    grp = _node("grp", "layout.group", "Prep", in_name=None, out_name=None)
    g = _graph([grp, _node("m", "data.load_csv", "M", group_id="grp")])
    assert '    subgraph g_grp["Prep"]' in to_mermaid(g).splitlines()
    blank = _node(
        "grp",
        "layout.group",
        "Prep",
        in_name=None,
        out_name=None,
        params=[Param(name="label", type_token="str", value="  ")],
    )
    g = _graph([blank, _node("m", "data.load_csv", "M", group_id="grp")])
    assert '    subgraph g_grp["Prep"]' in to_mermaid(g).splitlines()


def test_canvas_composite_and_callout_use_label_param() -> None:
    inner = _graph([_node("l1", "clean.impute_missing", "Impute")])
    comp = _node(
        "comp",
        "layout.composite",
        "Composite",
        subgraph=inner,
        params=[Param(name="label", type_token="str", value="Feature prep")],
    )
    out = to_mermaid(_graph([comp]))
    assert '    subgraph n_comp["Feature prep<br/><small>layout.composite</small>"]' in (
        out.splitlines()
    )
    callout = _node(
        "co",
        "layout.callout",
        "Callout",
        in_name=None,
        out_name=None,
        params=[Param(name="label", type_token="str", value="Key finding")],
    )
    out = to_mermaid(_graph([callout]), include_notes=True)
    assert 'n_co["Key finding' in out
    assert '"Callout' not in out


def test_non_param_titled_type_ignores_label_param() -> None:
    node = _node(
        "a", "data.load_csv", "Load", params=[Param(name="label", type_token="str", value="Other")]
    )
    out = to_mermaid(_graph([node]))
    assert 'n_a["Load' in out
    assert "Other" not in out


# ---------------------------------------------------------------------------
# Highlight of nodes not drawn individually
# ---------------------------------------------------------------------------


def _module_graph(*, group: bool = False) -> Graph:
    inner = _graph(
        [
            _node("l1", "nn.linear", "Lin"),
            _node("l2", "nn.relu", "R"),
            _node("hidden", "notes.markdown", "N", in_name=None, out_name=None),
        ],
        [_edge("l1", "l2")],
    )
    mod = _node("mod", "nn.module", "M", subgraph=inner, group_id="g" if group else None)
    src = _node("a", "data.load_csv", "Load", in_name=None)
    nodes = [src, mod]
    if group:
        nodes.append(_node("g", "layout.group", "Grp", in_name=None, out_name=None))
    return _graph(nodes, [_edge("a", "mod")])


def test_highlight_inner_node_of_collapsed_module_highlights_module() -> None:
    out = to_mermaid(_module_graph(), highlight=["l2"], max_nodes=2)
    assert "%% truncated:" in out
    assert "    class n_mod highlight" in out.splitlines()
    # A node that is not drawn at all (hidden note) has no stand-in.
    assert "highlight" not in to_mermaid(_module_graph(), highlight=["hidden"], max_nodes=2)


def test_highlight_inner_node_of_collapsed_composite_highlights_composite() -> None:
    inner = _graph([_node("c1", "t.a", "C1"), _node("c2", "t.b", "C2")], [_edge("c1", "c2")])
    comp = _node(
        "comp",
        "layout.composite",
        None,
        subgraph=inner,
        params=[Param(name="label", type_token="str", value="MyComp")],
    )
    src = _node("a", "data.load_csv", "Load", in_name=None)
    out = to_mermaid(_graph([src, comp], [_edge("a", "comp")]), highlight=["c2"], max_nodes=2)
    assert "    class n_comp highlight" in out.splitlines()


def test_highlight_inside_depth2_flattened_container_highlights_stand_in() -> None:
    deep = _graph([_node("d1", "t.d", "D")])
    inner = _graph(
        [_node("m2", "nn.module", "Inner", subgraph=deep), _node("x", "t.x", "X")],
        [_edge("m2", "x")],
    )
    outer = _node("mod", "nn.module", "Outer", subgraph=inner)
    out = to_mermaid(_graph([outer]), highlight=["d1"])
    lines = out.splitlines()
    assert "        %% flattened: nested subgraph of Inner (1 nodes) not shown" in lines
    assert "    class n_m2 highlight" in lines
    # In collapsed mode the top-level container stands for the whole nested tree.
    collapsed = to_mermaid(_graph([outer, _node("z", "t.z", "Z")]), highlight=["d1"], max_nodes=1)
    assert "    class n_mod highlight" in collapsed.splitlines()


def test_highlight_inner_node_of_module_in_collapsed_group() -> None:
    out = to_mermaid(_module_graph(group=True), highlight=["l2"], max_nodes=3)
    assert "    class g_g highlight" in out.splitlines()
    no_groups = to_mermaid(_module_graph(group=True), highlight=["l2"], groups=False, max_nodes=2)
    assert "    class n_mod highlight" in no_groups.splitlines()


def test_highlight_group_id_highlights_group_subgraph() -> None:
    lines = to_mermaid(_grouped(), highlight=["grp"]).splitlines()
    assert "    class g_grp highlight" in lines
    # Only the group itself, not its members.
    assert not any(line.startswith("    class n_") and "highlight" in line for line in lines)


def test_highlight_group_id_highlights_collapsed_group() -> None:
    out = to_mermaid(_grouped(), highlight=["grp"], max_nodes=2)
    assert '    g_grp["Prep<br/><small>2 nodes</small>"]' in out.splitlines()
    assert "    class g_grp highlight" in out.splitlines()


def test_highlight_group_id_ignored_when_groups_false() -> None:
    assert "highlight" not in to_mermaid(_grouped(), highlight=["grp"], groups=False)
    collapsed = to_mermaid(_grouped(), highlight=["grp"], groups=False, max_nodes=2)
    assert "highlight" not in collapsed
