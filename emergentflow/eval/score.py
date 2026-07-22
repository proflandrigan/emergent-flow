"""
emergentflow.eval.score
~~~~~~~~~~~~~~~~~~~~~~~~
Deterministic, scorer-based grading of an `ef.eval.run` compare table
(issue #93 part 2). Unlike `ef.eval.label` (human-supplied labels), `score()`
computes labels programmatically from a declarative list of scorer specs --
no client, no I/O, fully deterministic and cacheable.

`summarize_scores()` rolls a scored table up to one row per variant (mean of
each `score_*` column), mirroring `emergentflow.llm.aggregate.summarize_run`'s
role for cost/latency: a single tidy DataFrame the Prompt Lab compare grid
can render directly.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from emergentflow.api import public_op


class ScorerError(ValueError):
    """Raised by `score()` for an unknown scorer `kind` or a malformed scorer spec."""


def _score_exact_match(value: Any, spec: dict[str, Any], row: pd.Series) -> float:
    reference = row[spec["reference_column"]]
    case_sensitive = spec.get("case_sensitive", True)
    a, b = str(value), str(reference)
    if not case_sensitive:
        a, b = a.lower(), b.lower()
    return 1.0 if a == b else 0.0


def _score_contains(value: Any, spec: dict[str, Any], row: pd.Series) -> float:
    substring = str(spec["substring"])
    case_sensitive = spec.get("case_sensitive", True)
    haystack, needle = str(value), substring
    if not case_sensitive:
        haystack, needle = haystack.lower(), needle.lower()
    return 1.0 if needle in haystack else 0.0


def _score_regex(value: Any, spec: dict[str, Any], row: pd.Series) -> float:
    return 1.0 if re.search(spec["pattern"], str(value)) else 0.0


def _score_numeric_distance(value: Any, spec: dict[str, Any], row: pd.Series) -> float:
    reference = row[spec["reference_column"]]
    max_distance = spec["max_distance"]
    try:
        actual = float(value)
        expected = float(reference)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 if abs(actual - expected) <= max_distance else 0.0


_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _json_schema_violations(data: Any, schema: dict[str, Any]) -> list[str]:
    """A minimal structural JSON-Schema subset check: type/properties/required/items.

    Deliberately self-contained (not imported from `emergentflow.llm`'s private
    equivalent) -- scoped only to what eval.score needs.
    """
    schema_type = schema.get("type")
    if schema_type is not None:
        expected = _TYPE_MAP.get(schema_type)
        if expected is not None:
            if schema_type in ("integer", "number") and isinstance(data, bool):
                return [f"expected type {schema_type!r}, got bool"]
            if not isinstance(data, expected):
                return [f"expected type {schema_type!r}, got {type(data).__name__}"]

    errors: list[str] = []
    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"missing required property {req!r}")
        for key, sub_schema in schema.get("properties", {}).items():
            if key in data:
                errors.extend(_json_schema_violations(data[key], sub_schema))
    if isinstance(data, list):
        item_schema = schema.get("items")
        if item_schema is not None:
            for item in data:
                errors.extend(_json_schema_violations(item, item_schema))
    return errors


def _score_json_schema(value: Any, spec: dict[str, Any], row: pd.Series) -> float:
    schema = spec["schema"]
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return 0.0
    return 1.0 if not _json_schema_violations(data, schema) else 0.0


_SCORERS = {
    "exact_match": _score_exact_match,
    "contains": _score_contains,
    "regex": _score_regex,
    "numeric_distance": _score_numeric_distance,
    "json_schema": _score_json_schema,
}


@public_op(name="ef.eval.score")
def score(
    results_df: pd.DataFrame,
    scorers: list[dict[str, Any]],
    *,
    output_column: str = "output",
) -> pd.DataFrame:
    """Apply each scorer in *scorers* to *results_df*, appending `score_<name>` columns.

    Parameters
    ----------
    results_df:
        A tidy DataFrame with at least an *output_column* column (the shape
        `ef.eval.run` produces).
    scorers:
        A list of scorer specs, each a dict with required `name` (the result
        column suffix) and `kind` (one of `exact_match`, `contains`, `regex`,
        `numeric_distance`, `json_schema`), plus kind-specific keys:

        - `exact_match`: `reference_column` (str), optional `case_sensitive` (bool, default True)
        - `contains`: `substring` (str), optional `case_sensitive` (bool, default True)
        - `regex`: `pattern` (str)
        - `numeric_distance`: `reference_column` (str), `max_distance` (float)
        - `json_schema`: `schema` (dict, JSON Schema)
    output_column:
        Which column of *results_df* holds the LLM output to grade (default `"output"`).

    Returns
    -------
    pd.DataFrame
        A copy of *results_df* with one new `score_<name>` float column
        (0.0/1.0) per scorer, in `scorers` order.

    Raises
    ------
    ScorerError
        If a scorer spec is missing `name`/`kind`, or `kind` is unrecognized.
    """
    scored = results_df.copy()
    for spec in scorers:
        name = spec.get("name")
        kind = spec.get("kind")
        if not name or not kind:
            raise ScorerError(f"scorer spec missing 'name' or 'kind': {spec!r}")
        scorer_fn = _SCORERS.get(kind)
        if scorer_fn is None:
            raise ScorerError(f"unknown scorer kind {kind!r}; expected one of {sorted(_SCORERS)}")
        scored[f"score_{name}"] = [
            scorer_fn(row[output_column], spec, row) for _, row in scored.iterrows()
        ]
    return scored


@public_op(name="ef.eval.summarize_scores")
def summarize_scores(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Roll a `score()`-augmented table up to one row per variant.

    Derives `variant` as `provider + ":" + model` (same convention as
    `ef.eval.label`), then computes the mean of every `score_*` column plus a
    row count, grouped by variant.

    Parameters
    ----------
    scored_df:
        The output of `score()` -- must have `provider`, `model`, and at
        least one `score_*` column.

    Returns
    -------
    pd.DataFrame
        One row per variant, columns: `variant`, `n`, and `mean_<name>` for
        every `score_<name>` column found.

    Raises
    ------
    ValueError
        If *scored_df* has no `score_*` column.
    """
    score_columns = [c for c in scored_df.columns if c.startswith("score_")]
    if not score_columns:
        raise ValueError("summarize_scores: scored_df has no score_* column to summarize")

    df = scored_df.copy()
    df["variant"] = df["provider"] + ":" + df["model"]

    agg_spec: dict[str, tuple[str, str]] = {"n": ("variant", "size")}
    for col in score_columns:
        agg_spec["mean_" + col[len("score_") :]] = (col, "mean")

    return df.groupby("variant", as_index=False).agg(**agg_spec)
