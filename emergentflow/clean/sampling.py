"""
emergentflow.clean.sampling
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sampling and fuzzy-join verbs (Epic 16, Story 9): sample_rows, fuzzy_join.

``sample_rows`` is a thin wrapper over ``pandas.DataFrame.sample`` with an always-captured
seed, so a sampled pipeline is reproducible and the ADR-0002 equivalence gate holds.
``fuzzy_join`` is a string-similarity keyed merge behind the optional ``[fuzzy]`` extra
(rapidfuzz). Neither mutates its input.
"""

from __future__ import annotations

import importlib.util

import pandas as pd

from emergentflow.api import public_op

from .errors import (
    CleanError,
    ColumnCollisionError,
    MissingOptionalDependencyError,
    UnknownColumnError,
)

SAMPLE_MODES = ("random", "stratified", "top_n")
FUZZY_SCORERS = ("ratio", "partial_ratio", "token_sort_ratio", "token_set_ratio")
FUZZY_HOWS = ("inner", "left")


@public_op(name="ef.clean.sample_rows")
def sample_rows(
    df: pd.DataFrame,
    *,
    mode: str = "random",
    n: int | None = None,
    frac: float | None = None,
    by: list[str] | None = None,
    seed: int = 0,
) -> pd.DataFrame:
    """Draw a subset of rows, returning a NEW DataFrame.

    ``mode="random"`` samples uniformly; ``mode="stratified"`` samples within each group
    defined by ``by``; ``mode="top_n"`` takes the first ``n`` rows in existing order. Exactly
    one of ``n`` or ``frac`` is required for ``random``/``stratified``; ``top_n`` requires
    ``n``. The ``seed`` is **always captured** (default ``0``) so the same graph yields the
    same rows on every run — this is what keeps a sampled pipeline reproducible and the
    compiled/executed paths equivalent. Never mutates the input.
    """
    if mode not in SAMPLE_MODES:
        raise CleanError(f"unknown mode {mode!r}; expected one of {list(SAMPLE_MODES)!r}.")

    if mode == "top_n":
        if n is None:
            raise CleanError("mode 'top_n' requires 'n'.")
        if frac is not None:
            raise CleanError("mode 'top_n' does not accept 'frac'; use 'n'.")
    else:
        if (n is None) == (frac is None):
            raise CleanError(f"mode {mode!r} requires exactly one of 'n' or 'frac'.")

    if n is not None and n <= 0:
        raise CleanError(f"n must be a positive integer; got {n!r}.")
    if frac is not None and not (0 < frac <= 1):
        raise CleanError(f"frac must be in the interval (0, 1]; got {frac!r}.")

    if mode == "stratified":
        if not by:
            raise CleanError("mode 'stratified' requires a non-empty 'by' list of column names.")
        unknown = [c for c in by if c not in df.columns]
        if unknown:
            raise UnknownColumnError(
                f"unknown columns {unknown!r}; expected one of {list(df.columns)!r}."
            )

    if mode == "top_n":
        return df.head(n).copy()

    if mode == "random":
        if n is not None and n > len(df):
            raise CleanError(
                f"n={n} exceeds the number of available rows ({len(df)}); sample_rows draws "
                "without replacement, so n cannot exceed the row count."
            )
        return df.sample(n=n, frac=frac, random_state=seed)

    assert by is not None
    parts: list[pd.DataFrame] = []
    # dropna=False: a stratified sample must not silently discard rows whose 'by' key is
    # NaN -- they form their own stratum like any other group value, rather than vanishing
    # from the output with no error raised.
    for _key, group in df.groupby(by, sort=True, observed=True, dropna=False):
        if n is not None:
            take = min(n, len(group))
            parts.append(group.sample(n=take, random_state=seed))
        else:
            parts.append(group.sample(frac=frac, random_state=seed))
    if not parts:
        return df.head(0).copy()
    return pd.concat(parts).sort_index()


@public_op(name="ef.clean.fuzzy_join")
def fuzzy_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_on: str,
    right_on: str,
    threshold: float = 85.0,
    scorer: str = "ratio",
    how: str = "inner",
    limit: int = 1,
    suffixes: tuple[str, str] = ("_x", "_y"),
    score_column: str = "match_score",
) -> pd.DataFrame:
    """Merge two frames on a **string-similarity** match, returning a NEW DataFrame.

    Matches one left key column against one right key column by similarity rather than
    equality. ``threshold`` is a 0-100 rapidfuzz similarity score; only pairs scoring at or
    above it match. ``limit=1`` gives a one-to-one join (each left row takes its single best
    match); ``limit>1`` gives one-to-many. ``how="inner"`` drops unmatched left rows;
    ``how="left"`` keeps them with NaN on the right-hand columns. The realised similarity is
    written to ``score_column``. Requires the optional ``[fuzzy]`` extra. Never mutates
    either input.
    """
    if importlib.util.find_spec("rapidfuzz") is None:
        raise MissingOptionalDependencyError("emergentflow[fuzzy]")
    from rapidfuzz import fuzz, process

    if scorer not in FUZZY_SCORERS:
        raise CleanError(f"unknown scorer {scorer!r}; expected one of {list(FUZZY_SCORERS)!r}.")
    if how not in FUZZY_HOWS:
        raise CleanError(f"unknown how {how!r}; expected one of {list(FUZZY_HOWS)!r}.")
    if left_on not in left.columns:
        raise UnknownColumnError(
            f"unknown column {left_on!r} in left; expected one of {list(left.columns)!r}."
        )
    if right_on not in right.columns:
        raise UnknownColumnError(
            f"unknown column {right_on!r} in right; expected one of {list(right.columns)!r}."
        )
    if limit < 1:
        raise CleanError(f"limit must be at least 1; got {limit!r}.")
    if not (0 <= threshold <= 100):
        raise CleanError(f"threshold must be between 0 and 100; got {threshold!r}.")
    overlap = set(left.columns) & set(right.columns)
    final_left_columns = {f"{c}{suffixes[0]}" if c in overlap else c for c in left.columns}
    final_right_columns = {f"{c}{suffixes[1]}" if c in overlap else c for c in right.columns}
    if score_column in final_left_columns or score_column in final_right_columns:
        raise ColumnCollisionError(
            f"score column {score_column!r} collides with an existing (or suffix-renamed) "
            "column; choose a different score_column."
        )

    scorer_fn = getattr(fuzz, scorer)
    # A missing key (NaN/NA) stringifies to the literal text "nan" via astype(str); left
    # unguarded, two unrelated rows that are BOTH simply missing a key would then score a
    # perfect/high similarity match against each other. Right rows with a missing key are
    # therefore excluded from the candidate pool entirely (kept as unmatched, same as any
    # other below-threshold miss), and left rows with a missing key never attempt a match.
    right_key = right[right_on]
    valid_positions = [pos for pos, is_na in enumerate(right_key.isna()) if not is_na]
    right_values = right_key.astype(str).iloc[valid_positions].tolist()
    left_key = left[left_on]
    left_positions: list[int] = []
    right_positions: list[int] = []
    scores: list[float] = []
    for i, (value, is_na) in enumerate(zip(left_key.astype(str), left_key.isna(), strict=True)):
        matches = []
        if not is_na:
            matches = process.extract(
                value, right_values, scorer=scorer_fn, limit=limit, score_cutoff=threshold
            )
        if matches:
            for _choice, score, j in matches:
                left_positions.append(i)
                right_positions.append(valid_positions[j])
                scores.append(float(score))
        elif how == "left":
            left_positions.append(i)
            right_positions.append(-1)
            scores.append(float("nan"))

    left_part = left.iloc[left_positions].reset_index(drop=True)
    right_part = right.reset_index(drop=True).reindex(right_positions).reset_index(drop=True)
    if overlap:
        left_part = left_part.rename(columns={c: f"{c}{suffixes[0]}" for c in overlap})
        right_part = right_part.rename(columns={c: f"{c}{suffixes[1]}" for c in overlap})
    result = pd.concat([left_part, right_part], axis=1)
    result[score_column] = scores
    return result
