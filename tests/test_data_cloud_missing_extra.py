"""Base-install lane: a remote-URI load without the ``[cloud]`` extra raises a typed error.

Does not require fsspec to be absent from the dev venv — it monkeypatches the probe
(``importlib.util.find_spec``) so the gate behaves as if fsspec were not installed,
regardless of the actual dev environment.
"""

from __future__ import annotations

import builtins
import importlib.util

import pytest

from emergentflow.data import MissingOptionalDependencyError, load_csv


def test_missing_scheme_backend_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """fsspec present but the scheme-specific backend (e.g. s3fs) is not.

    ``_require_extra("emergentflow[cloud]")`` only probes for ``fsspec`` itself, not
    the per-scheme backend package (``s3fs``/``gcsfs``/``adlfs``) that fsspec lazily
    imports when it resolves a filesystem for a given URI. If fsspec is importable
    but, say, s3fs is not, fsspec.open() raises a bare ImportError -- this must still
    surface as the typed MissingOptionalDependencyError, not an opaque ImportError.
    """
    pytest.importorskip("fsspec")
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "s3fs" or name.startswith("s3fs."):
            raise ImportError("No module named 's3fs'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(MissingOptionalDependencyError) as exc_info:
        load_csv("s3://some-bucket/data.csv")

    assert "emergentflow[cloud]" in str(exc_info.value)


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
