"""``emergentflow`` console entry point (ADR 0013 Decision 2, §A6).

Subcommands:
- ``emergentflow serve`` -- boot the thin local canvas server (in-process ``ef.*``).
- ``emergentflow lab``   -- alias for ``serve`` (the JupyterLab-style launch verb).
- ``emergentflow run``   -- execute a graph from a file and record the run.
- ``emergentflow validate`` -- validate a graph from a file and print findings
  (``--strict`` exits non-zero on error-severity diagnostics).

Kept dependency-light: the server (and stdlib ``http.server``) is imported lazily
inside ``main`` so ``import emergentflow.cli`` stays cheap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emergentflow",
        description="Emergent Flow - local canvas + open-source data/ML SDK.",
    )
    sub = parser.add_subparsers(dest="command")
    for name in ("serve", "lab"):
        p = sub.add_parser(name, help="Boot the local canvas server (in-process ef.*).")
        p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
        p.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
        p.add_argument(
            "--no-browser",
            action="store_true",
            help="Do not open a browser tab on launch.",
        )
        p.add_argument(
            "--cache-dir",
            default=None,
            help=(
                "On-disk execution cache directory (Epic 7 Story 6). "
                "Default: .ef-cache under the current working directory."
            ),
        )
        p.add_argument(
            "--cache-max-mb",
            type=float,
            default=None,
            help="Execution cache size cap in MB, LRU-evicted above this. Default: 500.",
        )
        p.add_argument(
            "--runs-keep",
            type=int,
            default=None,
            help="Number of run history entries to keep. Default: 50.",
        )

    p = sub.add_parser("run", help="Execute a graph from a file and record the run.")
    p.add_argument("graph_file", help="Path to a .json graph file.")
    p.add_argument("--tag", default=None, help="Optional tag for this run (e.g. 'baseline').")
    p.add_argument(
        "--runs-keep",
        type=int,
        default=None,
        help="Number of run history entries to keep. Default: 50.",
    )
    p.add_argument(
        "--param",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help=(
            "Override a graph-level parameter (repeatable). The value is JSON-coerced and "
            "typed per the parameter's declared type_token, e.g. --param start_date=2026-02-01 "
            "--param min_events=10."
        ),
    )

    p = sub.add_parser("validate", help="Validate a graph from a file and print findings.")
    p.add_argument("graph_file", help="Path to a .json graph file.")
    p.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero when any error-severity diagnostic remains after "
            "suppression (Epic 17 validity gate)."
        ),
    )
    p.add_argument(
        "--suppressions",
        default=None,
        metavar="FILE",
        help=(
            "Path to a JSON file containing a list of [rule_id, node_id] pairs to "
            "suppress before deciding the exit code."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit the full Diagnostics result as JSON (machine-readable).",
    )

    p = sub.add_parser(
        "mcp",
        help="Run the stdio MCP bridge that forwards to a local server.",
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="Base URL of the local server (default: http://127.0.0.1:8765).",
    )
    p.add_argument(
        "--session-token",
        default=None,
        help=(
            "Bearer token for the server's session/MCP routes "
            "(default: $EMERGENTFLOW_SESSION_TOKEN)."
        ),
    )
    return parser


def _json_coerce(raw: str) -> Any:
    """Coerce a raw CLI value to JSON-native (numbers, bool, list, dict, quoted string)."""
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _coerce_param_value(raw: str, type_token: str) -> Any:
    """Coerce a ``--param`` value to the graph param's declared *type_token* (issue #116)."""
    value = _json_coerce(raw)
    if type_token in ("int", "float") and isinstance(value, bool):
        # json.loads parses "true"/"false" to real bools; a bool is never a valid
        # number (and isinstance(True, int) is True, so the int branch below would
        # otherwise accept --param p=true silently).
        raise ValueError(f"expected a number, got {raw!r}")
    if type_token == "int":
        if isinstance(value, int):
            return value
        # json.loads parses "10.5" to a float; truncating to 10 would silently
        # corrupt a bad value, so reject it instead (matching the ValueError the
        # string path raises for a non-numeric raw).
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"expected an integer value, got {raw!r}")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"expected an integer value, got {raw!r}") from exc
    if type_token == "float" and not isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"expected a number, got {raw!r}") from exc
    if type_token == "bool" and not isinstance(value, bool):
        # json.loads already parses "true"/"false" to real bools, but "1"/"0" arrive
        # as JSON numbers; the string tuple below would silently coerce --param flag=1
        # to False. Map numeric spellings by truthiness first.
        if isinstance(value, (int, float)):
            return value != 0
        return value in ("true", "True", "1", "yes")
    if type_token == "str" and not isinstance(value, str):
        return str(value)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in ("serve", "lab"):
        try:
            from emergentflow.server import serve
        except ModuleNotFoundError as exc:
            # fastapi/uvicorn ship in the optional `server` extra (Epic 7 Story 3).
            # A bare `pip install emergentflow` omits them; guide the user rather
            # than surfacing a raw ModuleNotFoundError traceback.
            print(
                f"`emergentflow {args.command}` needs the server extra "
                f"(missing dependency: {exc.name}).\n"
                "Install it with:  pip install 'emergentflow[server]'",
                file=sys.stderr,
            )
            return 1

        serve(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            cache_dir=args.cache_dir,
            cache_max_mb=args.cache_max_mb,
            runs_keep=args.runs_keep,
        )
        return 0

    if args.command == "run":
        import hashlib
        import json
        import pathlib
        import time as time_mod

        graph_path = pathlib.Path(args.graph_file)
        if not graph_path.is_file():
            print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
            return 1
        raw_text = graph_path.read_text(encoding="utf-8")
        graph_dict = json.loads(raw_text)

        # Configure and get the run store
        from emergentflow.server.runs import (
            DEFAULT_RUNS_DIRNAME,
            DEFAULT_RUNS_KEEP,
            configure_runs,
            get_default_runs,
        )

        runs_root = pathlib.Path.cwd() / DEFAULT_RUNS_DIRNAME
        resolved_keep = args.runs_keep if args.runs_keep is not None else DEFAULT_RUNS_KEEP
        configure_runs(runs_root, keep=resolved_keep)

        # Execute
        from emergentflow import __version__, execute
        from emergentflow.codegen.params import resolve_graph_params
        from emergentflow.ir.serialize import deserialize_graph
        from emergentflow.research.reproducibility import capture_run, resolve_dependency_versions
        from emergentflow.server.payload import to_payload

        graph = deserialize_graph(raw_text)

        params: dict[str, Any] = {}
        for item in args.param or []:
            if "=" not in item:
                print(f"Error: --param must be KEY=VALUE, got {item!r}", file=sys.stderr)
                return 1
            key, raw_value = item.split("=", 1)
            if key not in graph.params:
                print(
                    f"Error: --param names {key!r} which is not a graph-level parameter. "
                    f"Defined: {sorted(graph.params) or '(none)'}",
                    file=sys.stderr,
                )
                return 1
            try:
                params[key] = _coerce_param_value(raw_value, graph.params[key].type_token)
            except ValueError as exc:
                print(f"Error: --param {key!r}: {exc}", file=sys.stderr)
                return 1

        # Reject graphs with effectful (requires_client) nodes up front: the CLI does not
        # inject live clients, so such a node would fail mid-execution with a cryptic
        # MissingClientError instead of a clear, actionable message.
        from emergentflow.nodes import registry as _node_registry

        effectful = []
        for node in graph.nodes.values():
            definition_cls = _node_registry.try_get(node.type)
            if definition_cls is not None and definition_cls.required_client_kinds():
                effectful.append(node.id)
        if effectful:
            print(
                f"Error: graph contains node(s) {effectful!r} that require an injected "
                f"client (LLM call / warehouse / http); the `run` command does not "
                f"inject live clients yet — use `emergentflow serve` and execute via "
                f"the server instead.",
                file=sys.stderr,
            )
            return 1

        started_at = time_mod.time()
        results = execute(graph, params=params)
        finished_at = time_mod.time()

        graph_hash = hashlib.sha256(json.dumps(graph_dict, sort_keys=True).encode()).hexdigest()

        run_data = {
            "run_id": "",
            "tag": args.tag if args.tag else None,
            "graph_name": graph_dict.get("name", ""),
            "graph_hash": graph_hash,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at) * 1000),
            "node_count": len(graph_dict.get("nodes", {})),
            "statuses": {nid: {"status": "ok"} for nid in results},
            "reproducibility": {"seeds": {}, "content_hashes": {}, "dependency_versions": {}},
            "sdk_version": __version__,
        }

        # Build payloads (all ports, server-side _save_run_record filters to scalar/text/json)
        payloads: dict[str, dict[str, dict[str, Any]]] = {}
        for node_id, ports in results.items():
            payloads[node_id] = {}
            for port_name, value in ports.items():
                payloads[node_id][port_name] = to_payload(value)

        # Capture reproducibility
        try:
            deps = resolve_dependency_versions([])
            repro = capture_run(
                graph,
                dependency_versions=deps,
                # Record every graph-level param's RESOLVED value (stored value with any
                # --param override applied), not just the override keys -- a partial map
                # would make a multi-param run's record incomplete.
                params=resolve_graph_params(graph, overrides=params) if params else None,
            )
            run_data["reproducibility"] = {
                "seeds": repro.seeds,
                "content_hashes": repro.content_hashes,
                "dependency_versions": repro.dependency_versions,
                "params": repro.params,
            }
        except Exception:
            pass

        run_store = get_default_runs()
        run_id = run_store.save(run_data, graph_dict, payloads)

        print(f"Run recorded: {run_id}")
        if args.tag:
            print(f"  Tag: {args.tag}")
        print(f"  Nodes: {run_data['node_count']}")
        print(f"  Duration: {run_data['duration_ms']}ms")
        return 0

    if args.command == "validate":
        import json as json_mod
        import pathlib

        graph_path = pathlib.Path(args.graph_file)
        if not graph_path.is_file():
            print(f"Error: graph file not found: {graph_path}", file=sys.stderr)
            return 1
        raw_text = graph_path.read_text(encoding="utf-8")

        from emergentflow import apply_suppressions, validate
        from emergentflow.ir.serialize import deserialize_graph

        graph = deserialize_graph(raw_text)
        result = validate(graph)

        suppressions: list[list[str]] = []
        if args.suppressions:
            supp_path = pathlib.Path(args.suppressions)
            if not supp_path.is_file():
                print(f"Error: suppressions file not found: {supp_path}", file=sys.stderr)
                return 1
            suppressions = json_mod.loads(supp_path.read_text(encoding="utf-8"))

        filtered = apply_suppressions(result, suppressions)

        if args.json:
            print(json_mod.dumps(filtered.model_dump(mode="json"), indent=2))
        else:
            errors = [d for d in filtered.diagnostics if d.severity.value == "error"]
            warnings = [d for d in filtered.diagnostics if d.severity.value == "warning"]
            info = [d for d in filtered.diagnostics if d.severity.value == "info"]
            print(
                f"Validation: {len(filtered.diagnostics)} finding(s) "
                f"({len(errors)} error, {len(warnings)} warning, {len(info)} info)"
            )
            for d in filtered.diagnostics:
                tag = f"{d.severity.value}:"
                location = d.node_id or d.edge_id or "(graph)"
                rule = f" [{d.rule_id}]" if d.rule_id else ""
                print(f"  {tag} {location}: {d.message}{rule}")

        if args.strict:
            errors = [d for d in filtered.diagnostics if d.severity.value == "error"]
            return 1 if errors else 0
        return 0

    if args.command == "mcp":
        try:
            from emergentflow.collab.mcp_bridge import create_bridge_mcp_server
        except ModuleNotFoundError as exc:
            # fastmcp/httpx ship in the optional `mcp` extra. A bare
            # `pip install emergentflow` omits them; guide the user rather
            # than surfacing a raw ModuleNotFoundError traceback.
            print(
                f"`emergentflow mcp` needs the mcp extra "
                f"(missing dependency: {exc.name}).\n"
                "Install it with:  pip install 'emergentflow[mcp]'",
                file=sys.stderr,
            )
            return 1

        token = args.session_token or os.environ.get("EMERGENTFLOW_SESSION_TOKEN")
        try:
            # mcp.run(transport="stdio") is blocking and runs its own event loop,
            # so build the server (which does the catalog fetch) up front.
            mcp = asyncio.run(create_bridge_mcp_server(args.base_url, token=token))
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        mcp.run(transport="stdio")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
