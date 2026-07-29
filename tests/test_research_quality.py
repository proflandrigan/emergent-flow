"""Tests for emergentflow.research.quality (Epic 16, Story 19).

Focused on ``check_data_quality``'s error contract: what it raises, and with which typed
exception, when an expectation cannot be evaluated at all (as opposed to evaluating to a
violation). The passing/violating paths are additionally covered end to end through the
``research.assert_data`` reference node.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.research.errors import DataQualityError, ResearchError
from emergentflow.research.quality import check_data_quality


def _df() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": ["x", "y", "z"]})


def test_passing_expectations_return_the_frame_unchanged() -> None:
    frame = _df()
    result = check_data_quality(
        frame,
        [
            {"type": "non_null", "column": "a"},
            {"type": "range", "column": "a", "min": 0, "max": 10},
            {"type": "unique", "column": "b"},
            {"type": "row_count", "min": 1},
        ],
    )
    assert result is frame


def test_failing_expectation_raises_with_a_tidy_violations_frame() -> None:
    with pytest.raises(DataQualityError) as exc_info:
        check_data_quality(_df(), [{"type": "range", "column": "a", "min": 5}])
    violations = exc_info.value.violations
    assert list(violations.columns) == ["expectation", "column", "detail"]
    assert violations.iloc[0]["expectation"] == "range"


def test_unknown_expectation_type_is_typed() -> None:
    with pytest.raises(ResearchError, match="unknown expectation type"):
        check_data_quality(_df(), [{"type": "nope", "column": "a"}])


@pytest.mark.parametrize(
    ("etype", "extra"),
    [
        ("non_null", {}),
        ("range", {"min": 0}),
        ("unique", {}),
        ("allowed_values", {"values": [1]}),
        ("regex_match", {"pattern": "^x$"}),
    ],
)
def test_unknown_column_is_typed_not_a_bare_keyerror(etype: str, extra: dict[str, object]) -> None:
    """A column-scoped expectation naming a missing column must raise ``ResearchError``.

    Each check indexes ``frame[column]`` directly, so an absent column surfaced as a bare,
    undocumented ``KeyError`` -- opaque next to this module's own typed errors, and out of
    step with the rest of the SDK (``clean``'s ``UnknownColumnError``, ``stats``' "unknown
    columns [...]; expected one of [...]").
    """
    with pytest.raises(ResearchError, match="unknown column") as exc_info:
        check_data_quality(_df(), [{"type": etype, "column": "nope", **extra}])
    # The message must name the offending column and what was actually available.
    assert "'nope'" in str(exc_info.value)
    assert "'a'" in str(exc_info.value)


def test_row_count_stays_frame_scoped_and_needs_no_column() -> None:
    """``row_count`` carries no ``"column"``, so the guard must not reject it."""
    frame = _df()
    assert check_data_quality(frame, [{"type": "row_count", "min": 1, "max": 3}]) is frame


def test_schema_expectation_still_reports_missing_columns_as_violations() -> None:
    """``schema`` is exempt from the guard: reporting missing columns is its whole job."""
    with pytest.raises(DataQualityError) as exc_info:
        check_data_quality(_df(), [{"type": "schema", "columns": ["a", "b", "missing"]}])
    details = " ".join(exc_info.value.violations["detail"])
    assert "missing" in details
