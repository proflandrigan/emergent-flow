"""
tests/test_eval_run.py
~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `eval.run` node over a 2-input x
2-variant matrix, a determinism re-run proof, and the inspectable-return
check (Epic 9 Story 5).
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import is_inspectable
from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir import Direction, Edge, Graph, Port, PortRef, serialize_graph
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage
from emergentflow.llm.replay import ReplayClient, write_fixture
from emergentflow.llm.templating import render_prompt
from emergentflow.nodes.examples.eval_run import EvalRun
from emergentflow.nodes.examples.load_csv import LoadCsv

_SYSTEM = "You are {{persona}}."
_USER = "{{question}}"
_DATASET = [
    {"persona": "helpful", "question": "2+2?"},
    {"persona": "terse", "question": "capital of France?"},
]
_VARIANTS = [
    {"provider": "anthropic", "model": "claude-sonnet-5"},
    {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
]


def _seed_fixtures(fixtures_dir):
    """Write one fixture per (row, variant) cell -- 2x2 = 4 fixtures."""
    for row in _DATASET:
        spec = render_prompt(_SYSTEM, _USER, row)
        for variant in _VARIANTS:
            request = LLMRequest(
                provider=variant["provider"],
                model=variant["model"],
                messages=spec.messages,
                temperature=0.0,
                max_tokens=None,
                response_format="text",
                response_schema=None,
                api_key_env=None,
            )
            response = LLMResponse(
                text=f"answer:{row['question']}:{variant['model']}",
                data=None,
                model=variant["model"],
                usage=Usage(input_tokens=10, output_tokens=5),
                cost_usd=0.0,
                latency_ms=1.0,
                finish_reason="stop",
            )
            write_fixture(fixtures_dir, request, response)


def _node():
    return EvalRun().instantiate(system=_SYSTEM, user=_USER, variants=_VARIANTS)


def test_eval_run_golden_preview_code():
    """The node's codegen preview is deterministic, readable ef.eval.run(...) source."""
    node = _node()
    frag = EvalRun().preview(node)

    assert "ef.eval.run(" in frag.body
    assert "to_dict(orient='records')" in frag.body
    assert "client=client" in frag.body
    assert EvalRun().preview(node).body == frag.body


def test_eval_run_node_equivalence_2x2(tmp_path):
    """execute() and the codegen preview (exec'd) produce an identical 2x2 compare table."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()
    dataset_df = pd.DataFrame(_DATASET)

    # codegen side: preview() references bare "dataset" and "client" names
    # (mirrors tests/test_llm_prompt.py's established node-granularity
    # equivalence pattern for nodes with a required IN port).
    frag = EvalRun().preview(node)
    scope = {"dataset": dataset_df, "client": client}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["results"]

    exec_result = EvalRun().execute(node, {"dataset": dataset_df}, client=client)["results"]

    pd.testing.assert_frame_equal(codegen_result, exec_result)
    assert exec_result.shape == (4, 11)
    assert list(exec_result["row_id"]) == [0, 0, 1, 1]
    assert all(isinstance(m, list) and len(m) > 0 for m in exec_result["messages"])
    assert set(exec_result["model"]) == {"claude-sonnet-5", "claude-haiku-4-5-20251001"}
    assert set(exec_result["output"]) == {
        "answer:2+2?:claude-sonnet-5",
        "answer:2+2?:claude-haiku-4-5-20251001",
        "answer:capital of France?:claude-sonnet-5",
        "answer:capital of France?:claude-haiku-4-5-20251001",
    }


def test_eval_run_determinism(tmp_path):
    """Re-running the same dataset/variants under the same ReplayClient is byte-identical."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()
    dataset_df = pd.DataFrame(_DATASET)

    first = EvalRun().execute(node, {"dataset": dataset_df}, client=client)["results"]
    second = EvalRun().execute(node, {"dataset": dataset_df}, client=client)["results"]

    pd.testing.assert_frame_equal(first, second)


def test_eval_run_result_is_inspectable(tmp_path):
    """The compare table satisfies the @public_op inspectable-return contract."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()
    dataset_df = pd.DataFrame(_DATASET)

    result = EvalRun().execute(node, {"dataset": dataset_df}, client=client)["results"]
    assert is_inspectable(result)


def _out_port(node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name: str) -> Port:
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def test_eval_run_no_api_key_in_ir_or_code(monkeypatch):
    """A secret VALUE never appears in serialized IR or emitted code -- only the NAME does."""
    secret_value = "sk-super-secret-value-should-never-appear-1234567890"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)

    node = EvalRun().instantiate(
        system=_SYSTEM,
        user=_USER,
        variants=[
            {
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
        ],
    )
    # eval.run's `dataset` IN port is required, so compile_to_code/serialize_graph need it
    # wired to an upstream DataFrame-producing node (LoadCsv, the simplest such node).
    load_csv_node = LoadCsv().instantiate(path="x.csv")
    edge = Edge(
        source=PortRef(node_id=load_csv_node.id, port_id=_out_port(load_csv_node, "frame").id),
        target=PortRef(node_id=node.id, port_id=_in_port(node, "dataset").id),
    )
    graph = Graph(
        nodes={load_csv_node.id: load_csv_node, node.id: node},
        edges={edge.id: edge},
    )

    ir_json = serialize_graph(graph)
    code = compile_to_code(graph)

    assert secret_value not in ir_json
    assert secret_value not in code
    # The env-var NAME is expected to appear -- that's the whole point of ADR 0017. It now also
    # appears in the compiled module's docstring hint (Epic 9 Story 9 / Task 15), in addition to
    # the codegen call site.
    assert "ANTHROPIC_API_KEY" in ir_json
    assert "ANTHROPIC_API_KEY" in code
