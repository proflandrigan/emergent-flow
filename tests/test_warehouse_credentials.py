"""Tests for warehouse credential resolution at the effect edge (Epic 13 Story 3).

Mirrors the style of `tests/test_llm_env.py`-style env-var tests: `monkeypatch`
sets/unsets `os.environ` per test, never real secrets.
"""

from __future__ import annotations

import pytest

from emergentflow.data.warehouse.credentials import (
    MissingConnectionCredentialError,
    required_env_vars,
    resolve_credentials,
)
from emergentflow.data.warehouse.profiles import ConnectionProfile


def _profile(**credential_refs: str) -> ConnectionProfile:
    return ConnectionProfile(
        name="warehouse_prod",
        dialect="postgres",
        auth_method="password_env",
        credential_refs=credential_refs,
    )


def test_resolve_env_ref_strips_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPASSWORD", "s3cr3t")
    profile = _profile(password_env="PGPASSWORD")

    resolved = resolve_credentials(profile)

    assert resolved == {"password": "s3cr3t"}


def test_resolve_missing_env_raises_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGPASSWORD", raising=False)
    profile = _profile(password_env="PGPASSWORD")

    with pytest.raises(MissingConnectionCredentialError) as exc_info:
        resolve_credentials(profile)

    message = str(exc_info.value)
    assert "PGPASSWORD" in message
    assert "s3cr3t" not in message


def test_resolve_passthrough_non_env_ref() -> None:
    profile = _profile(keyring_handle="svc/acct")

    resolved = resolve_credentials(profile)

    assert resolved == {"keyring_handle": "svc/acct"}


def test_required_env_vars_lists_only_env_keys() -> None:
    profile = _profile(password_env="PGPASSWORD", keyring_handle="svc/acct")

    assert required_env_vars(profile) == ["PGPASSWORD"]
