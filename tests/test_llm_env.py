"""Tests for emergentflow.llm.env.resolve_effective_api_key_env_name."""

from __future__ import annotations

import pytest

from emergentflow.connections.profiles import LlmConnectionProfile, ProfileStore, save_profiles
from emergentflow.llm.env import MissingAPIKeyError, resolve_effective_api_key_env_name


def _register(tmp_path, monkeypatch, profile) -> None:
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
    store = ProfileStore()
    store.add(profile)
    save_profiles(store)


def test_llm_connection_resolves_profiles_api_key_env(tmp_path, monkeypatch) -> None:
    _register(
        tmp_path,
        monkeypatch,
        LlmConnectionProfile(name="prof", provider="openai", api_key_env="MY_OPENAI_KEY"),
    )
    result = resolve_effective_api_key_env_name("openai", None, "prof")
    assert result == "MY_OPENAI_KEY"


def test_unknown_llm_connection_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(tmp_path / "connections.toml"))
    with pytest.raises(MissingAPIKeyError) as exc_info:
        resolve_effective_api_key_env_name("openai", None, "nope")
    assert "nope" in str(exc_info.value)


def test_non_llm_kind_profile_rejected(tmp_path, monkeypatch) -> None:
    from emergentflow.connections.profiles import WarehouseConnectionProfile

    _register(tmp_path, monkeypatch, WarehouseConnectionProfile(name="wh", dialect="duckdb"))
    with pytest.raises(MissingAPIKeyError) as exc_info:
        resolve_effective_api_key_env_name("openai", None, "wh")
    assert "wh" in str(exc_info.value)


def test_no_llm_connection_falls_back_to_api_key_env() -> None:
    result = resolve_effective_api_key_env_name("openai", "EXPLICIT_ENV", None)
    assert result == "EXPLICIT_ENV"


def test_no_llm_connection_no_api_key_env_falls_back_to_provider_default() -> None:
    result = resolve_effective_api_key_env_name("anthropic", None, None)
    assert result == "ANTHROPIC_API_KEY"
