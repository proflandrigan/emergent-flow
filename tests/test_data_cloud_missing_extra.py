"""Base-install lane: a remote-URI load without the ``[cloud]`` extra raises a typed error.

Does not require fsspec to be absent from the dev venv — it monkeypatches the probe
(``importlib.util.find_spec``) so the gate behaves as if fsspec were not installed,
regardless of the actual dev environment.
"""

from __future__ import annotations

import importlib.util

import pytest

from emergentflow.data import MissingOptionalDependencyError, load_csv


def test_missing_cloud_extra_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name == "fsspec":
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(MissingOptionalDependencyError) as exc_info:
        load_csv("s3://bucket/key.csv")

    assert "emergentflow[cloud]" in str(exc_info.value)
