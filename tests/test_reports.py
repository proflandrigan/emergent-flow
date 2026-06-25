# NOTE: this module is slow — ydata-profiling is heavy to import and run, so
# datasets here are kept intentionally tiny.
"""Tests for ``emergentflow.reports`` (Epic 1, Story 8)."""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.reports import generate_html_summary


def _tiny_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4, 5],
            "b": ["x", "y", "z", "x", "y"],
        }
    )


def test_generate_returns_html_string() -> None:
    df = _tiny_df()

    html = generate_html_summary(df)

    assert isinstance(html, str)
    assert len(html) > 0
    assert "<html" in html.lower()


def test_generate_includes_title() -> None:
    df = _tiny_df()

    html = generate_html_summary(df, title="My Report")

    assert "My Report" in html


def test_generate_empty_df_raises() -> None:
    with pytest.raises(ValueError):
        generate_html_summary(pd.DataFrame())


def test_generate_registered_as_public_op() -> None:
    from emergentflow.api import PUBLIC_OPS

    assert "ef.reports.generate_html_summary" in PUBLIC_OPS


def test_generate_does_not_mutate_input() -> None:
    df = _tiny_df()
    copy = df.copy()

    generate_html_summary(df)

    assert df.equals(copy)
