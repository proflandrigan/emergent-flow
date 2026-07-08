"""Tests for emergentflow.data.warehouse.profiles."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergentflow.data.warehouse.profiles import (
    ConnectionProfile,
    ProfileStore,
    UnknownConnectionError,
    load_profiles,
)
from emergentflow.data.warehouse.profiles import test_connection as probe_connection


def _make_profile(**overrides: object) -> ConnectionProfile:
    fields: dict[str, object] = {
        "name": "warehouse_prod",
        "dialect": "postgres",
        "coordinates": {"host": "db.internal", "port": "5432", "database": "analytics"},
        "auth_method": "password_env",
        "credential_refs": {"password_env": "PGPASSWORD"},
        "limits": {"max_rows": 100000},
    }
    fields.update(overrides)
    return ConnectionProfile(**fields)  # type: ignore[arg-type]


def test_profile_is_secret_free_round_trip() -> None:
    profile = _make_profile()
    dumped = profile.model_dump()
    assert ConnectionProfile(**dumped) == profile

    dumped_json = profile.model_dump_json()
    assert "PGPASSWORD" in dumped_json  # the env-var NAME, not a secret value, is fine

    forbidden = {"password", "token", "key", "secret"}
    field_names = set(ConnectionProfile.model_fields)
    assert not (field_names & forbidden)


def test_unknown_dialect_rejected() -> None:
    with pytest.raises(ValidationError):
        ConnectionProfile(name="x", dialect="nope")


def test_store_get_unknown_raises() -> None:
    store = ProfileStore()
    store.add(_make_profile(name="warehouse_prod"))
    with pytest.raises(UnknownConnectionError) as exc_info:
        store.get("missing")
    message = str(exc_info.value)
    assert "missing" in message
    assert "warehouse_prod" in message


def test_store_names_sorted_and_contains() -> None:
    store = ProfileStore()
    store.add(_make_profile(name="warehouse_staging", dialect="duckdb"))
    store.add(_make_profile(name="warehouse_prod"))
    assert store.names() == ["warehouse_prod", "warehouse_staging"]
    assert "warehouse_prod" in store
    assert "nope" not in store


def test_load_profiles_from_toml(tmp_path: Path) -> None:
    toml_text = """
[warehouse_prod]
dialect = "postgres"
auth_method = "password_env"

[warehouse_prod.coordinates]
host = "db.internal"
port = "5432"
database = "analytics"

[warehouse_prod.credential_refs]
password_env = "PGPASSWORD"

[warehouse_prod.limits]
max_rows = 100000
""".strip()
    path = tmp_path / "connections.toml"
    path.write_text(toml_text)

    store = load_profiles(path)
    assert store.names() == ["warehouse_prod"]

    profile = store.get("warehouse_prod")
    assert profile.dialect == "postgres"
    assert profile.coordinates == {
        "host": "db.internal",
        "port": "5432",
        "database": "analytics",
    }
    assert profile.credential_refs == {"password_env": "PGPASSWORD"}
    assert profile.limits == {"max_rows": 100000}


def test_load_profiles_missing_file_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "nope.toml"
    assert load_profiles(path).names() == []


def test_test_connection_structural_ok() -> None:
    profile = _make_profile()
    result = probe_connection(profile)
    assert result.ok is True
    assert result.name == profile.name


def test_test_connection_probe_failure_reported() -> None:
    profile = _make_profile()

    class FailingClient:
        def list_relations(self, connection: object, **kwargs: object) -> object:
            raise RuntimeError("boom")

    result = probe_connection(profile, client=FailingClient())
    assert result.ok is False
    assert "boom" in result.message
