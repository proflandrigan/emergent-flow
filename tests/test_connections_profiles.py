"""Tests for emergentflow.connections.profiles."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from emergentflow.connections.profiles import (
    LlmConnectionProfile,
    ProfileStore,
    UnknownConnectionError,
    WarehouseConnectionProfile,
    load_profiles,
    save_profiles,
)
from emergentflow.connections.profiles import (
    test_connection as probe_connection,
)


def _make_warehouse_profile(**overrides: object) -> WarehouseConnectionProfile:
    fields: dict[str, object] = {
        "name": "warehouse_prod",
        "dialect": "postgres",
        "coordinates": {"host": "db.internal", "port": "5432", "database": "analytics"},
        "auth_method": "password_env",
        "credential_refs": {"password_env": "PGPASSWORD"},
        "limits": {"max_rows": 100000},
    }
    fields.update(overrides)
    return WarehouseConnectionProfile(**fields)  # type: ignore[arg-type]


def _make_llm_profile(**overrides: object) -> LlmConnectionProfile:
    fields: dict[str, object] = {
        "name": "my_openai_key",
        "provider": "openai",
        "api_key_env": "OPENAI_API_KEY",
    }
    fields.update(overrides)
    return LlmConnectionProfile(**fields)  # type: ignore[arg-type]


def test_profiles_are_secret_free() -> None:
    warehouse = _make_warehouse_profile()
    dumped = warehouse.model_dump()
    WarehouseConnectionProfile(**dumped)

    llm = _make_llm_profile()
    dumped_llm = llm.model_dump()
    LlmConnectionProfile(**dumped_llm)

    forbidden = {"password", "token", "key", "secret"}
    wh_field_names = set(WarehouseConnectionProfile.model_fields)
    assert not (wh_field_names & forbidden), (
        f"WarehouseConnectionProfile has forbidden field(s): {wh_field_names & forbidden}"
    )
    llm_field_names = set(LlmConnectionProfile.model_fields)
    assert not (llm_field_names & forbidden), (
        f"LlmConnectionProfile has forbidden field(s): {llm_field_names & forbidden}"
    )


def test_warehouse_unknown_dialect_rejected() -> None:
    with pytest.raises(ValidationError):
        WarehouseConnectionProfile(name="x", dialect="nope")


def test_llm_empty_api_key_env_rejected() -> None:
    with pytest.raises(ValidationError):
        LlmConnectionProfile(name="x", provider="openai", api_key_env="")


def test_store_get_unknown_raises() -> None:
    store = ProfileStore()
    store.add(_make_warehouse_profile(name="warehouse_prod"))
    with pytest.raises(UnknownConnectionError) as exc_info:
        store.get("missing")
    message = str(exc_info.value)
    assert "missing" in message
    assert "warehouse_prod" in message


def test_store_remove() -> None:
    store = ProfileStore()
    store.add(_make_warehouse_profile(name="warehouse_prod"))

    store.remove("warehouse_prod")
    with pytest.raises(UnknownConnectionError):
        store.get("warehouse_prod")

    with pytest.raises(UnknownConnectionError) as exc_info:
        store.remove("nope")
    message = str(exc_info.value)
    assert "nope" in message


def test_store_names_and_list_filter_by_kind() -> None:
    store = ProfileStore()
    store.add(_make_warehouse_profile(name="warehouse_prod"))
    store.add(_make_llm_profile(name="my_openai_key"))

    assert store.names() == ["my_openai_key", "warehouse_prod"]
    assert store.names(kind="warehouse") == ["warehouse_prod"]
    assert store.names(kind="llm") == ["my_openai_key"]

    all_profiles = store.list()
    assert len(all_profiles) == 2

    wh_list = store.list(kind="warehouse")
    assert len(wh_list) == 1
    assert wh_list[0].name == "warehouse_prod"
    assert isinstance(wh_list[0], WarehouseConnectionProfile)

    llm_list = store.list(kind="llm")
    assert len(llm_list) == 1
    assert llm_list[0].name == "my_openai_key"
    assert isinstance(llm_list[0], LlmConnectionProfile)


def test_load_profiles_backward_compatible_kind(tmp_path: Path) -> None:
    toml_text = """
[warehouse_prod]
dialect = "postgres"
auth_method = "password_env"

[warehouse_prod.coordinates]
host = "db.internal"

[warehouse_prod.credential_refs]
password_env = "PGPASSWORD"
""".strip()
    path = tmp_path / "connections.toml"
    path.write_text(toml_text)

    store = load_profiles(path)
    profile = store.get("warehouse_prod")
    assert profile.kind == "warehouse"
    assert isinstance(profile, WarehouseConnectionProfile)
    assert profile.dialect == "postgres"


def test_load_profiles_table_key_wins_over_body_name(tmp_path: Path) -> None:
    """A `name` field inside a table body must not override the TOML table key."""
    toml_text = """
[aliased]
kind = "llm"
provider = "openai"
api_key_env = "OPENAI_API_KEY"
name = "sneaky"
""".strip()
    path = tmp_path / "connections.toml"
    path.write_text(toml_text)

    store = load_profiles(path)
    profile = store.get("aliased")
    assert profile.name == "aliased"
    with pytest.raises(UnknownConnectionError):
        store.get("sneaky")


def test_load_profiles_llm_profile(tmp_path: Path) -> None:
    toml_text = """
[my_openai_key]
kind = "llm"
provider = "openai"
api_key_env = "OPENAI_API_KEY"
""".strip()
    path = tmp_path / "connections.toml"
    path.write_text(toml_text)

    store = load_profiles(path)
    profile = store.get("my_openai_key")
    assert profile.kind == "llm"
    assert isinstance(profile, LlmConnectionProfile)
    assert profile.provider == "openai"
    assert profile.api_key_env == "OPENAI_API_KEY"


def test_load_profiles_missing_file_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "nope.toml"
    store = load_profiles(path)
    assert store.names() == []


def test_save_load_round_trip(tmp_path: Path) -> None:
    store = ProfileStore()
    store.add(_make_warehouse_profile(name="warehouse_prod"))
    store.add(_make_llm_profile(name="my_openai_key"))

    save_path = tmp_path / "connections.toml"
    save_profiles(store, save_path)

    reloaded = load_profiles(save_path)
    assert reloaded.names() == ["my_openai_key", "warehouse_prod"]

    wh = reloaded.get("warehouse_prod")
    assert isinstance(wh, WarehouseConnectionProfile)
    assert wh.dialect == "postgres"
    assert wh.coordinates == {"host": "db.internal", "port": "5432", "database": "analytics"}
    assert wh.auth_method == "password_env"
    assert wh.credential_refs == {"password_env": "PGPASSWORD"}

    llm = reloaded.get("my_openai_key")
    assert isinstance(llm, LlmConnectionProfile)
    assert llm.provider == "openai"
    assert llm.api_key_env == "OPENAI_API_KEY"


def test_save_profiles_creates_parent_dirs(tmp_path: Path) -> None:
    store = ProfileStore()
    store.add(_make_warehouse_profile(name="warehouse_prod"))

    save_path = tmp_path / "nested" / "dir" / "connections.toml"
    save_profiles(store, save_path)

    assert save_path.exists()


def test_test_connection_structural_ok() -> None:
    profile = _make_warehouse_profile()
    result = probe_connection(profile)
    assert result.ok is True
    assert result.name == profile.name


def test_test_connection_probe_failure_reported() -> None:
    profile = _make_warehouse_profile()

    class FailingClient:
        def list_relations(self, connection: object, **kwargs: object) -> object:
            raise RuntimeError("boom")

    result = probe_connection(profile, client=FailingClient())
    assert result.ok is False
    assert "boom" in result.message
