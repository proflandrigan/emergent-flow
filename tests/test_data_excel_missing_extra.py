"""Base-install lane: a load_excel call without the ``[excel]`` extra raises a typed error.

Does not require openpyxl to be absent from the dev venv — it monkeypatches the probe
(``importlib.util.find_spec``) so the gate behaves as if openpyxl were not installed,
regardless of the actual dev environment.
"""

from __future__ import annotations

import importlib.util

import pytest

from emergentflow.data import MissingOptionalDependencyError, load_excel


def test_missing_excel_extra_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "openpyxl":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(MissingOptionalDependencyError) as exc_info:
        load_excel("x.xlsx")

    assert "emergentflow[excel]" in str(exc_info.value)
