"""compare_metrics percent change must share the sign of the delta, even for a negative baseline."""

from __future__ import annotations

from emergentflow.collab.metrics import compare_metrics


def test_delta_pct_sign_matches_delta_for_negative_baseline() -> None:
    out = compare_metrics(-10.0, -5.0)  # improved by 5
    assert out["delta"] == 5.0
    assert out["delta_pct"] == 50.0


def test_delta_pct_positive_baseline_unchanged() -> None:
    assert compare_metrics(10.0, 15.0)["delta_pct"] == 50.0
    assert compare_metrics(0.0, 1.0)["delta_pct"] is None
