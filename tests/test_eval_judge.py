"""
tests/test_eval_judge.py
~~~~~~~~~~~~~~~~~~~~~~~~
Golden + ADR-0002 equivalence tests for the `eval.judge` node over a 2-row
output fixture, a determinism re-run proof, and the inspectable-return check.
"""

from __future__ import annotations

import pandas as pd

from emergentflow.api import is_inspectable
from emergentflow.eval.judge import JUDGE_RESPONSE_SCHEMA, judge_messages
from emergentflow.llm.protocol import LLMRequest, LLMResponse, Usage
from emergentflow.llm.replay import ReplayClient, write_fixture
from emergentflow.nodes.examples.eval_judge import EvalJudge

_RUBRIC = "Score 1.0 if the answer is factually correct and concise, 0.0 otherwise."
_JUDGE_PROVIDER = "anthropic"
_JUDGE_MODEL = "claude-sonnet-5"

_RESULTS_DF = pd.DataFrame(
    {
        "row_id": [0, 1],
        "input": [{"q": "2+2?"}, {"q": "capital of France?"}],
        "provider": ["anthropic", "anthropic"],
        "model": ["claude-sonnet-5", "claude-sonnet-5"],
        "output": ["The answer is 4.", "The capital of France is Paris."],
        "input_tokens": [10, 12],
        "output_tokens": [5, 6],
        "cost_usd": [0.0, 0.0],
        "latency_ms": [1.0, 1.2],
        "finish_reason": ["stop", "stop"],
    }
)

_EXPECTED_SCORES = [1.0, 0.8]
_EXPECTED_RATIONALES = ["Correct and clear.", "Correct but could be more concise."]


def _seed_fixtures(fixtures_dir):
    """Write one fixture per row (2 rows)."""
    for i, (_, row) in enumerate(_RESULTS_DF.iterrows()):
        messages = tuple(dict(m) for m in judge_messages(_RUBRIC, row["output"]))
        request = LLMRequest(
            provider=_JUDGE_PROVIDER,
            model=_JUDGE_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=None,
            response_format="json",
            response_schema=JUDGE_RESPONSE_SCHEMA,
        )
        response = LLMResponse(
            text=None,
            data={"score": _EXPECTED_SCORES[i], "rationale": _EXPECTED_RATIONALES[i]},
            model=_JUDGE_MODEL,
            usage=Usage(input_tokens=8, output_tokens=4),
            cost_usd=0.0,
            latency_ms=1.0,
            finish_reason="stop",
        )
        write_fixture(fixtures_dir, request, response)


def _node():
    return EvalJudge().instantiate(
        rubric=_RUBRIC,
        judge_provider=_JUDGE_PROVIDER,
        judge_model=_JUDGE_MODEL,
    )


def test_eval_judge_golden_preview_code():
    """The node's codegen preview is deterministic, readable ef.eval.judge(...) source."""
    node = _node()
    frag = EvalJudge().preview(node)

    assert "ef.eval.judge(" in frag.body
    assert "client=client" in frag.body
    assert EvalJudge().preview(node).body == frag.body


def test_eval_judge_node_equivalence_2row(tmp_path):
    """execute() and the codegen preview (exec'd) produce an identical judged DataFrame."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()

    # codegen side: preview() references bare "results" and "client" names
    frag = EvalJudge().preview(node)
    scope = {"results": _RESULTS_DF, "client": client}
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    codegen_result = scope["judged"]

    exec_result = EvalJudge().execute(node, {"results": _RESULTS_DF}, client=client)["judged"]

    pd.testing.assert_frame_equal(codegen_result, exec_result)
    assert list(exec_result["judge_score"]) == _EXPECTED_SCORES
    assert list(exec_result["judge_rationale"]) == _EXPECTED_RATIONALES
    assert exec_result.shape == (2, len(_RESULTS_DF.columns) + 2)


def test_eval_judge_determinism(tmp_path):
    """Re-running under the same ReplayClient is byte-identical."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()

    first = EvalJudge().execute(node, {"results": _RESULTS_DF}, client=client)["judged"]
    second = EvalJudge().execute(node, {"results": _RESULTS_DF}, client=client)["judged"]

    pd.testing.assert_frame_equal(first, second)


def test_eval_judge_result_is_inspectable(tmp_path):
    """The judged DataFrame satisfies the @public_op inspectable-return contract."""
    _seed_fixtures(tmp_path)
    client = ReplayClient(tmp_path)
    node = _node()

    result = EvalJudge().execute(node, {"results": _RESULTS_DF}, client=client)["judged"]
    assert is_inspectable(result)


# Secret-hygiene test is intentionally omitted for `eval.judge`: unlike
# `eval.run`, whose variants dict carries an `api_key_env` key per variant,
# `eval.judge`'s params have no `api_key_env`/`llm_connection` field --
# credentials are resolved entirely inside `ef.llm.call` via the same
# injected-LLMClient seam. The EvalJudge node itself never touches env-var
# names, so the secret VALUE can never leak into the IR or emitted code
# through a param whose name isn't even declared. Adding an `api_key_env`
# param purely for this test would be scope-creep beyond what issue #93
# specifies.
