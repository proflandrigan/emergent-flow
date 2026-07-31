"""Tests for the ``emergentflow`` console entry point (ADR 0013 Decision 2)."""

from __future__ import annotations

import builtins
from typing import Any

from emergentflow.cli import main


def _patch_serve(monkeypatch) -> dict[str, Any]:
    import emergentflow.server as server_pkg

    calls: dict[str, Any] = {}

    def fake_serve(
        host: str,
        port: int,
        open_browser: bool = True,
        cache_dir: str | None = None,
        cache_max_mb: float | None = None,
        runs_keep: int | None = None,
    ) -> None:
        calls.update(
            host=host,
            port=port,
            open_browser=open_browser,
            cache_dir=cache_dir,
            cache_max_mb=cache_max_mb,
            runs_keep=runs_keep,
        )

    monkeypatch.setattr(server_pkg, "serve", fake_serve)
    return calls


def test_serve_opens_browser_by_default(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["serve"]) == 0
    assert calls["open_browser"] is True
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8765


def test_serve_no_browser_flag(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["serve", "--no-browser", "--port", "9999"]) == 0
    assert calls["open_browser"] is False
    assert calls["port"] == 9999


def test_lab_alias_also_serves(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["lab"]) == 0
    assert calls["open_browser"] is True


def test_serve_without_extra_prints_hint(monkeypatch, capsys) -> None:
    # fastapi/uvicorn live in the optional `server` extra (Epic 7 Story 3); a bare
    # install must surface an install hint, not a raw ModuleNotFoundError traceback.
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "emergentflow.server" or name.startswith("emergentflow.server"):
            raise ModuleNotFoundError("No module named 'fastapi'", name="fastapi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rc = main(["serve"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "emergentflow[server]" in err
    assert "fastapi" in err


def test_no_command_prints_help_and_returns_1(capsys) -> None:
    assert main([]) == 1
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_serve_cache_flags_default_to_none(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["serve"]) == 0
    assert calls["cache_dir"] is None
    assert calls["cache_max_mb"] is None
    assert calls["runs_keep"] is None


def test_serve_cache_flags_are_forwarded(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["serve", "--cache-dir", "/tmp/mycache", "--cache-max-mb", "250"]) == 0
    assert calls["cache_dir"] == "/tmp/mycache"
    assert calls["cache_max_mb"] == 250.0


def test_lab_cache_flags_are_forwarded(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["lab", "--cache-dir", "/tmp/labcache"]) == 0
    assert calls["cache_dir"] == "/tmp/labcache"


def test_serve_runs_keep_forwarded(monkeypatch) -> None:
    calls = _patch_serve(monkeypatch)
    assert main(["serve", "--runs-keep", "100"]) == 0
    assert calls["runs_keep"] == 100
