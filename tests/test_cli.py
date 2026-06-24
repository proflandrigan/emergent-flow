"""Tests for the ``colonymind`` console entry point (ADR 0013 Decision 2)."""

from __future__ import annotations

from typing import Any

from colonymind.cli import main


def _patch_serve(monkeypatch) -> dict[str, Any]:
    import colonymind.server as server_pkg

    calls: dict[str, Any] = {}

    def fake_serve(host: str, port: int, open_browser: bool = True) -> None:
        calls.update(host=host, port=port, open_browser=open_browser)

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


def test_no_command_prints_help_and_returns_1() -> None:
    assert main([]) == 1
