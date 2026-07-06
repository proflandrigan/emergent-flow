"""
emergentflow.viz.spec
~~~~~~~~~~~~~~~~~~~~~~
The single chart-call validation gate for the viz archetype (Epic 12, Story 2/3).

``_prepare_chart_spec`` is the one place a chart call is validated, shared by both the compiled-code
path and ``execute`` because both reach a chart through ``ef.viz.plot``, which calls this gate
(mirroring ``emergentflow.stats.spec._prepare_model_spec``). It validates the chart key, that every
encoding/option kwarg is on the chart's allow-list, and that encoding values referencing columns
exist in the frame. Does not mutate the frame or the passed dicts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from emergentflow.viz.errors import InvalidEncodingError
from emergentflow.viz.registry import ChartSpec, get_chart_spec


def _prepare_chart_spec(
    df: pd.DataFrame,
    chart: str,
    encoding: dict[str, Any],
    options: dict[str, Any],
) -> tuple[ChartSpec, dict[str, Any], dict[str, Any]]:
    """Validate a chart call; return ``(chart_spec, normalized_encoding, normalized_options)``.

    Raises :class:`~emergentflow.viz.errors.UnknownChartError` (via ``get_chart_spec``) for an
    unknown chart key, and :class:`~emergentflow.viz.errors.InvalidEncodingError` for an
    encoding/option kwarg not on the chart's allow-list, or an encoding value naming a column that
    is not in *df*.
    """
    chart_spec = get_chart_spec(chart)

    bad_enc = sorted(set(encoding) - set(chart_spec.encodings))
    if bad_enc:
        raise InvalidEncodingError(
            f"chart {chart!r} does not accept encoding(s) {bad_enc!r}; "
            f"accepted: {sorted(chart_spec.encodings)!r}."
        )
    bad_opt = sorted(set(options) - set(chart_spec.options))
    if bad_opt:
        raise InvalidEncodingError(
            f"chart {chart!r} does not accept option(s) {bad_opt!r}; "
            f"accepted: {sorted(chart_spec.options)!r}."
        )

    columns = set(df.columns)
    for key, value in encoding.items():
        if isinstance(value, dict):
            refs: list[Any] = list(value.keys())
        elif isinstance(value, (list, tuple)):
            refs = list(value)
        else:
            refs = [value]
        for ref in refs:
            if isinstance(ref, str) and ref not in columns:
                raise InvalidEncodingError(
                    f"encoding {key!r} references column {ref!r}, which is not in the input "
                    f"frame; available columns: {sorted(columns)!r}."
                )

    return chart_spec, dict(encoding), dict(options)
