"""Tests for emergentflow.clean.pii (Epic 16, Story 21) -- goldens for both the base
regex engine and the optional presidio NER engine.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from emergentflow.clean.errors import CleanError, MissingOptionalDependencyError
from emergentflow.clean.pii import PII_CATEGORIES, redact_pii


def _frame():
    return pd.DataFrame(
        {
            "note": [
                "email me at ada@example.com",
                "my number is 555-123-4567",
                "nothing sensitive here",
            ]
        }
    )


def test_regex_engine_masks_email_and_phone():
    result = redact_pii(_frame(), columns=["note"])
    assert "ada@example.com" not in result["note"].iloc[0]
    assert "555-123-4567" not in result["note"].iloc[1]
    assert result["note"].iloc[2] == "nothing sensitive here"


def test_regex_engine_is_default():
    result = redact_pii(_frame(), columns=["note"])
    result_explicit = redact_pii(_frame(), columns=["note"], engine="regex")
    pd.testing.assert_frame_equal(result, result_explicit)


def test_unknown_engine_raises():
    with pytest.raises(CleanError):
        redact_pii(_frame(), columns=["note"], engine="not-a-real-engine")


def test_unknown_category_raises():
    with pytest.raises(CleanError):
        redact_pii(_frame(), columns=["note"], categories=["not-a-real-category"])


def test_does_not_mutate_input():
    frame = _frame()
    original = frame.copy()
    redact_pii(frame, columns=["note"])
    pd.testing.assert_frame_equal(frame, original)


def test_presidio_engine_without_extra_raises_typed_error():
    """presidio is NOT installed in this environment -- verify the typed-error path."""
    if "presidio_analyzer" in sys.modules or "presidio_anonymizer" in sys.modules:
        pytest.skip("presidio is actually installed in this environment; typed-error path N/A")
    with pytest.raises(MissingOptionalDependencyError) as exc_info:
        redact_pii(_frame(), columns=["note"], engine="presidio")
    assert "pii" in str(exc_info.value)


def test_presidio_engine_success_path_monkeypatched(monkeypatch):
    """Monkeypatch fake presidio_analyzer/presidio_anonymizer modules into sys.modules so the
    engine="presidio" success path can be exercised without the real (heavy, spaCy-model-
    requiring) library installed -- mirrors the weasyprint monkeypatch precedent used for
    build_report(render_pdf=True) in Story 16.
    """
    analyzer_module = types.ModuleType("presidio_analyzer")

    class _FakeRecognizerResult:
        pass

    class _FakeAnalyzerEngine:
        def analyze(self, *, text, language, entities):
            return [_FakeRecognizerResult()] if "@" in text else []

    analyzer_module.AnalyzerEngine = _FakeAnalyzerEngine

    anonymizer_module = types.ModuleType("presidio_anonymizer")
    entities_module = types.ModuleType("presidio_anonymizer.entities")

    class _FakeOperatorConfig:
        def __init__(self, operator_name, params):
            self.operator_name = operator_name
            self.params = params

    class _FakeAnonymizeResult:
        def __init__(self, text):
            self.text = text

    class _FakeAnonymizerEngine:
        def anonymize(self, *, text, analyzer_results, operators):
            if analyzer_results:
                mask = operators["DEFAULT"].params["new_value"]
                return _FakeAnonymizeResult(mask)
            return _FakeAnonymizeResult(text)

    anonymizer_module.AnonymizerEngine = _FakeAnonymizerEngine
    entities_module.OperatorConfig = _FakeOperatorConfig
    anonymizer_module.entities = entities_module

    monkeypatch.setitem(sys.modules, "presidio_analyzer", analyzer_module)
    monkeypatch.setitem(sys.modules, "presidio_anonymizer", anonymizer_module)
    monkeypatch.setitem(sys.modules, "presidio_anonymizer.entities", entities_module)

    import importlib.util

    real_find_spec = importlib.util.find_spec

    def _fake_find_spec(name, *args, **kwargs):
        if name in ("presidio_analyzer", "presidio_anonymizer"):
            return object()
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)

    result = redact_pii(_frame(), columns=["note"], categories=["email"], engine="presidio")
    assert result["note"].iloc[0] == "[REDACTED]"
    assert result["note"].iloc[2] == "nothing sensitive here"


def test_pii_categories_cover_story_21_list():
    assert set(PII_CATEGORIES) == {"email", "phone", "ssn", "credit_card"}
