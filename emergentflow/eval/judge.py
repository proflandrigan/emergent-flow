"""
emergentflow.eval.judge
~~~~~~~~~~~~~~~~~~~~~~~~
LLM-as-judge scoring of an `ef.eval.run` compare table (issue #93 part 2,
the counterpart to `emergentflow.eval.score`'s deterministic scorers).
`judge()` asks an LLM to grade each row against a free-text rubric via
`emergentflow.llm.call`, following the same client-injection seam as
`ef.eval.run` (ADR 0017) -- not cacheable, needs an injected `LLMClient`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.llm import call
from emergentflow.llm.protocol import LLMClient

JUDGE_SYSTEM_PROMPT = (
    "You are an impartial grader. Score the given output against the rubric on a "
    "scale from 0.0 (fails) to 1.0 (fully meets the rubric). Respond with JSON: "
    '{"score": <float>, "rationale": <string>}.'
)

JUDGE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["score", "rationale"],
    "properties": {
        "score": {"type": "number"},
        "rationale": {"type": "string"},
    },
}


def judge_messages(rubric: str, output_value: Any) -> list[dict[str, str]]:
    """Build the {system, user} messages sent to the judge model for one row.

    A standalone, non-underscore-prefixed helper (not just an inline literal
    inside `judge()`) so tests can construct matching `LLMRequest` fixtures
    for `ReplayClient` without duplicating the exact prompt text by hand --
    mirrors how `tests/test_eval_run.py` imports the public `render_prompt`
    to build its own fixture requests.
    """
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Rubric: {rubric}\n\nOutput to grade:\n{output_value}"},
    ]


@public_op(name="ef.eval.judge")
def judge(
    results_df: pd.DataFrame,
    rubric: str,
    *,
    judge_provider: str,
    judge_model: str,
    client: LLMClient | None,
    output_column: str = "output",
) -> pd.DataFrame:
    """Grade each row of *results_df* with an LLM judge against *rubric*.

    For each row, calls `emergentflow.llm.call` with `judge_messages(rubric,
    row[output_column])`, requesting structured JSON output validated against
    `JUDGE_RESPONSE_SCHEMA` (`{"score": float, "rationale": str}`).

    Parameters
    ----------
    results_df:
        A tidy DataFrame with at least an *output_column* column (the shape
        `ef.eval.run` produces).
    rubric:
        Free-text grading criteria, e.g. "Score 1.0 if the answer is
        factually correct and concise, 0.0 otherwise."
    judge_provider, judge_model:
        The provider/model to use as the judge (may differ from the variant
        being judged).
    client:
        The injected `LLMClient` (ADR 0017) every call delegates to.
    output_column:
        Which column of *results_df* holds the text to grade (default `"output"`).

    Returns
    -------
    pd.DataFrame
        A copy of *results_df* with two new columns: `judge_score` (float)
        and `judge_rationale` (str).

    Raises
    ------
    MissingClientError
        If *client* is ``None`` (propagated from `emergentflow.llm.call`).
    StructuredOutputValidationError
        If the judge model's JSON output doesn't match `JUDGE_RESPONSE_SCHEMA`
        (propagated from `emergentflow.llm.call`).
    """
    judged = results_df.copy()
    scores: list[float] = []
    rationales: list[str] = []
    for _, row in judged.iterrows():
        response = call(
            judge_messages(rubric, row[output_column]),
            provider=judge_provider,
            model=judge_model,
            client=client,
            response_format="json",
            response_schema=JUDGE_RESPONSE_SCHEMA,
        )
        data = response.data or {}
        scores.append(float(data.get("score", 0.0)))
        rationales.append(str(data.get("rationale", "")))
    judged["judge_score"] = scores
    judged["judge_rationale"] = rationales
    return judged
