"""
emergentflow.clean.pii
~~~~~~~~~~~~~~~~~~~~~~~
PII detection + masking (Epic 16, Story 21).

``redact_pii`` runs regex-based PII detection and masking in the base install (email, phone,
SSN-like, credit-card-like patterns; ``engine="regex"``, the default). NER-based detection via
presidio (``engine="presidio"``) is gated behind the optional ``[pii]`` extra, raising a typed
``MissingOptionalDependencyError`` when it's absent. Non-mutating -- always returns a new
frame. Positioned to run right after ingestion, before any PII reaches a report or a downstream
node.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.clean.errors import CleanError, MissingOptionalDependencyError, UnknownColumnError

__all__ = ["PII_CATEGORIES", "PRESIDIO_ENTITY_MAP", "DEFAULT_MASK", "REDACT_ENGINES", "redact_pii"]

#: Regex-based PII categories available in the base install. Each is a best-effort pattern,
#: not an authoritative validator -- false positives/negatives are expected and acceptable for
#: a first-pass redaction gate.
PII_CATEGORIES: dict[str, str] = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{1,4}\b",
}

#: Our category names, mapped to presidio's built-in recognizer entity names -- used only by
#: the ``engine="presidio"`` path, so the caller-facing category vocabulary stays identical
#: across both engines.
PRESIDIO_ENTITY_MAP: dict[str, str] = {
    "email": "EMAIL_ADDRESS",
    "phone": "PHONE_NUMBER",
    "ssn": "US_SSN",
    "credit_card": "CREDIT_CARD",
}

REDACT_ENGINES = ("regex", "presidio")

DEFAULT_MASK = "[REDACTED]"


def _redact_regex(
    df: pd.DataFrame, *, columns: list[str], categories: list[str], mask: str
) -> pd.DataFrame:
    result = df.copy()
    for column in columns:
        series = result[column].astype("string")
        for category in categories:
            pattern = PII_CATEGORIES[category]
            series = series.str.replace(pattern, mask, regex=True)
        result[column] = series
    return result


def _require_presidio() -> None:
    if (
        importlib.util.find_spec("presidio_analyzer") is None
        or importlib.util.find_spec("presidio_anonymizer") is None
    ):
        raise MissingOptionalDependencyError("emergentflow[pii]")


def _redact_presidio(
    df: pd.DataFrame, *, columns: list[str], categories: list[str], mask: str
) -> pd.DataFrame:
    _require_presidio()
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    entities = [PRESIDIO_ENTITY_MAP[category] for category in categories]
    operators = {"DEFAULT": OperatorConfig("replace", {"new_value": mask})}

    def _redact_cell(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        findings = analyzer.analyze(text=value, language="en", entities=entities)
        return anonymizer.anonymize(text=value, analyzer_results=findings, operators=operators).text

    result = df.copy()
    for column in columns:
        result[column] = result[column].apply(_redact_cell)
    return result


@public_op(name="ef.clean.redact_pii")
def redact_pii(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    categories: list[str] | None = None,
    mask: str = DEFAULT_MASK,
    engine: str = "regex",
) -> pd.DataFrame:
    """Detect and mask common PII patterns in *df*'s text columns. Never mutates *df*.

    Parameters
    ----------
    df:
        The DataFrame to redact.
    columns:
        Columns to scan. Defaults to every ``object``/string-dtype column when not given.
    categories:
        Which :data:`PII_CATEGORIES` to apply, in order. Defaults to every category
        (``email``, ``phone``, ``ssn``, ``credit_card``) when not given. The same category
        vocabulary is used regardless of *engine* (mapped internally to presidio's own entity
        names for ``engine="presidio"`` via :data:`PRESIDIO_ENTITY_MAP`).
    mask:
        Replacement text for each match. Default ``"[REDACTED]"``.
    engine:
        ``"regex"`` (default, base install) or ``"presidio"`` (NER-based detection, requires
        the optional ``[pii]`` extra).

    Returns
    -------
    pd.DataFrame
        A new frame with matches in the target columns replaced by *mask*. Non-target columns
        and non-matching cells are unchanged. Target columns come back as pandas' nullable
        ``string`` dtype under ``engine="regex"``, or plain ``object`` dtype under
        ``engine="presidio"`` (presidio's anonymizer returns plain ``str``).

    Raises
    ------
    UnknownColumnError
        If a name in *columns* is not a column of *df*.
    CleanError
        If a name in *categories* is not one of :data:`PII_CATEGORIES`, or *engine* is not one
        of :data:`REDACT_ENGINES`.
    MissingOptionalDependencyError
        If ``engine="presidio"`` and the ``[pii]`` extra is not installed.
    """
    if engine not in REDACT_ENGINES:
        raise CleanError(f"unknown engine {engine!r}; expected one of {REDACT_ENGINES!r}.")

    if columns is None:
        target_columns = [
            c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
        ]
    else:
        unknown_columns = [c for c in columns if c not in df.columns]
        if unknown_columns:
            raise UnknownColumnError(
                f"unknown columns {unknown_columns!r}; expected one of {list(df.columns)!r}."
            )
        target_columns = list(columns)

    target_categories = list(categories) if categories is not None else list(PII_CATEGORIES)
    unknown_categories = [c for c in target_categories if c not in PII_CATEGORIES]
    if unknown_categories:
        raise CleanError(
            f"unknown PII categories {unknown_categories!r}; "
            f"expected one of {list(PII_CATEGORIES)!r}."
        )

    if engine == "presidio":
        return _redact_presidio(df, columns=target_columns, categories=target_categories, mask=mask)
    return _redact_regex(df, columns=target_columns, categories=target_categories, mask=mask)
