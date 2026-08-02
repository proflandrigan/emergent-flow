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


def _write_graph(path, nodes: dict, edges: dict | None = None) -> None:
    import json

    payload = {"schema_version": 2, "name": "test", "nodes": nodes, "edges": edges or {}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _simple_node(node_id: str, node_type: str, ports=None, params=None) -> dict:
    return {"id": node_id, "type": node_type, "ports": ports or [], "params": params or []}


def _port(port_id: str, name: str, direction: str) -> dict:
    return {"id": port_id, "name": name, "direction": direction, "data_type": "DataFrame"}


def _leaky_graph(tmp_path) -> dict:
    """Write a leaky graph (scale_features upstream of train_test_split)."""
    from emergentflow.ir import Direction

    graph_file = tmp_path / "leaky.json"
    _write_graph(
        graph_file,
        nodes={
            "scale": _simple_node(
                "scale",
                "transform.scale_features",
                ports=[
                    _port("si", "in", Direction.IN.value),
                    _port("so", "out", Direction.OUT.value),
                ],
            ),
            "split": _simple_node(
                "split",
                "ml.train_test_split",
                ports=[
                    _port("spi", "in", Direction.IN.value),
                    _port("spt", "train", Direction.OUT.value),
                    _port("spx", "test", Direction.OUT.value),
                ],
            ),
        },
        edges={
            "e1": {
                "id": "e1",
                "source": {"node_id": "scale", "port_id": "so"},
                "target": {"node_id": "split", "port_id": "spi"},
            }
        },
    )
    return graph_file


def test_validate_clean_graph_exits_zero(tmp_path) -> None:
    from emergentflow.ir import Direction

    graph_file = tmp_path / "clean.json"
    _write_graph(
        graph_file,
        nodes={
            "n-src": _simple_node(
                "n-src",
                "test.source",
                ports=[_port("p-out", "out", Direction.OUT.value)],
            ),
        },
    )
    assert main(["validate", str(graph_file)]) == 0


def test_validate_leaky_graph_non_strict_exits_zero(tmp_path) -> None:
    graph_file = _leaky_graph(tmp_path)
    # non-strict: findings printed, exit 0
    assert main(["validate", str(graph_file)]) == 0
    # strict: error-severity validity finding remains -> exit 1
    assert main(["validate", str(graph_file), "--strict"]) == 1


def test_validate_strict_with_suppressions_exits_zero(tmp_path) -> None:
    import json as json_mod

    graph_file = _leaky_graph(tmp_path)
    supp = tmp_path / "supp.json"
    supp.write_text(json_mod.dumps([["fit_before_split", "scale"]]), encoding="utf-8")
    # suppressing the error-severity finding makes strict pass
    assert main(["validate", str(graph_file), "--strict", "--suppressions", str(supp)]) == 0


def test_validate_missing_file_returns_1(tmp_path) -> None:
    assert main(["validate", str(tmp_path / "nope.json")]) == 1


def test_validate_json_output_is_valid(tmp_path) -> None:
    import io
    import json as json_mod
    from contextlib import redirect_stdout

    from emergentflow.ir import Direction

    graph_file = tmp_path / "clean.json"
    _write_graph(
        graph_file,
        nodes={
            "n-src": _simple_node(
                "n-src",
                "test.source",
                ports=[_port("p-out", "out", Direction.OUT.value)],
            ),
        },
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["validate", str(graph_file), "--json"])
    assert rc == 0
    data = json_mod.loads(buf.getvalue())
    assert "diagnostics" in data and "edge_compatibility" in data
