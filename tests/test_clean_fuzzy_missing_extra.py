"""Base-install lane: a ``fuzzy_join`` without the ``[fuzzy]`` extra raises a typed error.

Does not require rapidfuzz to be absent from the dev venv — it monkeypatches the probe
(``importlib.util.find_spec``) so the gate behaves as if rapidfuzz were not installed,
regardless of the actual dev environment. Mirrors
``tests/test_data_cloud_missing_extra.py``.
"""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from emergentflow.clean import MissingOptionalDependencyError, fuzzy_join


def _left() -> pd.DataFrame:
    return pd.DataFrame({"name": ["Apple Inc", "Microsft Corp"], "lid": [1, 2]})


def _right() -> pd.DataFrame:
    return pd.DataFrame({"company": ["Apple Inc.", "Microsoft Corp"], "rid": [10, 20]})


def test_missing_fuzzy_extra_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "rapidfuzz":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(MissingOptionalDependencyError) as exc_info:
        fuzzy_join(_left(), _right(), left_on="name", right_on="company")

    assert "emergentflow[fuzzy]" in str(exc_info.value)


def test_missing_extra_is_raised_before_any_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extra gate must fire ahead of the param checks.

    Otherwise a base-install user with an unrelated typo in their params would get a
    ``CleanError`` about the typo and never learn the real problem is the missing extra.
    """
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "rapidfuzz":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    # Every one of these params is invalid; the extra gate must still win.
    with pytest.raises(MissingOptionalDependencyError):
        fuzzy_join(
            _left(),
            _right(),
            left_on="nope",
            right_on="also_nope",
            scorer="bogus",
            how="bogus",
            limit=0,
            threshold=999.0,
        )
