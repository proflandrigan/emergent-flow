"""Regression tests: connection-profile persistence must be atomic and race-free."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import tomli_w

from emergentflow.connections import profiles as profiles_mod
from emergentflow.connections.profiles import (
    LlmConnectionProfile,
    ProfileStore,
    load_profiles,
    save_profiles,
)
from emergentflow.server import service


def _llm(name: str) -> LlmConnectionProfile:
    return LlmConnectionProfile(name=name, provider="openai", api_key_env="K")


def test_save_profiles_failure_keeps_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "connections.toml"
    save_profiles(ProfileStore({"a": _llm("a")}), path)
    before = path.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(tomli_w, "dump", boom)
    with pytest.raises(RuntimeError):
        save_profiles(ProfileStore({"a": _llm("a"), "b": _llm("b")}), path)
    assert path.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.name != "connections.toml"]


def test_concurrent_create_connection_loses_no_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "connections.toml"
    monkeypatch.setenv("EMERGENTFLOW_CONNECTIONS", str(path))
    real_load = profiles_mod.load_profiles

    def slow_load(*a: object, **k: object) -> ProfileStore:
        store = real_load(*a, **k)  # type: ignore[arg-type]
        time.sleep(0.2)  # widen the read-modify-write window
        return store

    monkeypatch.setattr(profiles_mod, "load_profiles", slow_load)
    bodies = [
        {"name": n, "kind": "llm", "provider": "openai", "api_key_env": "K"} for n in ("x", "y")
    ]
    threads = [threading.Thread(target=service.create_connection, args=(b,)) for b in bodies]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(load_profiles(path).names()) == ["x", "y"]
