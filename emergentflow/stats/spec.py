"""
emergentflow.stats.spec
~~~~~~~~~~~~~~~~~~~~~~~~
The single structured-spec validation gate for the stats model archetypes (Epic 12, Story 3).

``_prepare_model_spec`` is the one place a model's structured spec is validated, shared by both
the compiled-code path and ``execute`` because both reach a model through ``ef.stats.fit_model``,
which calls this gate at fit time (mirroring how ``_prepare_declarative`` is the single gate shared
by the compiler and executor). Both paths therefore accept/reject identical ``(df, model, spec)``
triples by construction -- there is no second, drifting validator.

Column-existence checks live here (not in ``compile_to_code``) because ``fit_model`` runs the gate
with the real DataFrame in hand on both paths. Family/link compatibility and categorical/numeric
coherence checks extend this gate as the GLM/MixedLM families land (Epic 12 Stories 4-5); today it
validates model-key existence, required/allowed spec fields, and column existence for the
column-bearing fields (``target`` / ``fixed_effects`` / ``random_effects`` / ``groups``).
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from emergentflow.stats.diagnostics import DiagnosticSpec, get_diagnostic_spec
from emergentflow.stats.errors import InvalidModelSpecError
from emergentflow.stats.registry import ModelSpec, get_model_spec

#: Structured-spec fields whose value is a single column name (validated against df.columns).
_SCALAR_COLUMN_FIELDS = ("target", "groups", "weights")
#: Structured-spec fields whose value is a list of column names.
_LIST_COLUMN_FIELDS = ("fixed_effects", "random_effects", "linear_terms")


def _prepare_model_spec(
    df: pd.DataFrame, model: str, spec: dict[str, Any]
) -> tuple[ModelSpec, dict[str, Any]]:
    """Validate *spec* for *model* against *df*; return ``(model_spec, normalized_spec)``.

    The single shared gate (see module docstring). Raises
    :class:`~emergentflow.stats.errors.UnknownModelError` (via ``get_model_spec``) for an
    unregistered model key, and :class:`~emergentflow.stats.errors.InvalidModelSpecError` for:

    * an unknown spec field (not in the model's required + optional fields),
    * a missing/empty required spec field,
    * a ``target`` / ``groups`` value that is not a column of *df*,
    * a ``fixed_effects`` / ``random_effects`` entry that is not a column of *df*.

    Does not mutate *df* or *spec*; returns a shallow-copied normalized spec dict.
    """
    model_spec = get_model_spec(model)

    allowed = set(model_spec.required_spec_fields) | set(model_spec.optional_spec_fields)
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise InvalidModelSpecError(
            f"unknown spec field(s) {unknown!r} for model {model!r}; "
            f"allowed fields are {sorted(allowed)!r}."
        )

    missing = [f for f in model_spec.required_spec_fields if spec.get(f) in (None, "", [], ())]
    if missing:
        raise InvalidModelSpecError(f"model {model!r} requires spec field(s) {missing!r}.")

    columns = set(df.columns)

    for field in _SCALAR_COLUMN_FIELDS:
        value = spec.get(field)
        if value is not None and value not in columns:
            raise InvalidModelSpecError(
                f"spec {field!r} {value!r} is not a column of the input frame; "
                f"available columns: {sorted(columns)!r}."
            )

    for field in _LIST_COLUMN_FIELDS:
        value = spec.get(field)
        if value is not None and not isinstance(value, (list, tuple)):
            raise InvalidModelSpecError(
                f"spec {field!r} must be a list of column names, got {type(value).__name__}."
            )
        for col in value or []:
            if col not in columns:
                raise InvalidModelSpecError(
                    f"spec {field!r} references column {col!r}, which is not in the input "
                    f"frame; available columns: {sorted(columns)!r}."
                )

    if "family" in spec and spec["family"] is not None:
        from emergentflow.stats.catalog import _GLM_FAMILIES, _GLM_LINKS

        family = spec["family"]
        if family not in _GLM_FAMILIES:
            raise InvalidModelSpecError(
                f"unknown GLM family {family!r}; expected one of {sorted(_GLM_FAMILIES)!r}."
            )
        link = spec.get("link")
        if link is not None and link not in _GLM_LINKS[family]:
            raise InvalidModelSpecError(
                f"link {link!r} is not valid for family {family!r}; "
                f"expected one of {sorted(_GLM_LINKS[family])!r}."
            )

    normalized = dict(spec)
    try:
        json.dumps(normalized, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidModelSpecError(
            f"spec for model {model!r} must be JSON-native (got a non-serializable value: {exc})."
        ) from exc

    return model_spec, normalized


def _prepare_diagnostic_spec(
    df: pd.DataFrame | None,
    model: Any,
    diagnostic: str,
    spec: dict[str, Any],
) -> tuple[DiagnosticSpec, dict[str, Any]]:
    """Validate *spec* for *diagnostic* against *df*/*model*; return (diag_spec, normalized).

    The single shared gate for the diagnostic archetype (the ``_prepare_model_spec`` analog).
    Raises :class:`~emergentflow.stats.errors.UnknownDiagnosticError` for an unregistered key,
    and :class:`~emergentflow.stats.errors.InvalidModelSpecError` for: a missing required input
    (``df`` when ``needs_frame``, ``model`` when ``needs_model``), an unknown spec field, a
    missing/empty required spec field, or a ``columns``-style spec field referencing a column
    not in *df* (only checked when *df* is given).
    """
    diag_spec = get_diagnostic_spec(diagnostic)

    if diag_spec.needs_frame and df is None:
        raise InvalidModelSpecError(f"diagnostic {diagnostic!r} requires a DataFrame input.")
    if diag_spec.needs_model and model is None:
        raise InvalidModelSpecError(
            f"diagnostic {diagnostic!r} requires a fitted StatsModel input."
        )

    allowed = set(diag_spec.required_spec_fields) | set(diag_spec.optional_spec_fields)
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise InvalidModelSpecError(
            f"unknown spec field(s) {unknown!r} for diagnostic {diagnostic!r}; "
            f"allowed fields are {sorted(allowed)!r}."
        )

    missing = [f for f in diag_spec.required_spec_fields if spec.get(f) in (None, "", [], ())]
    if missing:
        raise InvalidModelSpecError(
            f"diagnostic {diagnostic!r} requires spec field(s) {missing!r}."
        )

    if df is not None:
        columns = set(df.columns)
        value = spec.get("columns")
        if value is not None:
            if not isinstance(value, (list, tuple)):
                raise InvalidModelSpecError(
                    f"spec 'columns' must be a list of column names, got {type(value).__name__}."
                )
            for col in value:
                if col not in columns:
                    raise InvalidModelSpecError(
                        f"spec 'columns' references column {col!r}, which is not in the input "
                        f"frame; available columns: {sorted(columns)!r}."
                    )

    normalized = dict(spec)
    try:
        json.dumps(normalized, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidModelSpecError(
            f"spec for diagnostic {diagnostic!r} must be JSON-native "
            f"(got a non-serializable value: {exc})."
        ) from exc

    return diag_spec, normalized
