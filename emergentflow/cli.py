"""``emergentflow`` console entry point (ADR 0013 Decision 2, §A6).

Subcommands:
- ``emergentflow serve`` -- boot the thin local canvas server (in-process ``ef.*``).
- ``emergentflow lab``   -- alias for ``serve`` (the JupyterLab-style launch verb).
- ``emergentflow run``   -- execute a graph from a file and record the run.

Kept dependency-light: the server (and stdlib ``http.server``) is imported lazily
inside ``main`` so ``import emergentflow.cli`` stays cheap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time as time_mod
from collections.abc import Sequence


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
    return parser


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
        from emergentflow.ir.serialize import deserialize_graph
        from emergentflow.research.reproducibility import capture_run, resolve_dependency_versions
        from emergentflow.server.payload import to_payload

        graph = deserialize_graph(raw_text)

        started_at = time_mod.time()
        results = execute(graph)
        finished_at = time_mod.time()

        graph_hash = hashlib.sha256(json.dumps(graph_dict, sort_keys=True).encode()).hexdigest()

        run_data = {
            "run_id": "",
            "tag": args.tag,
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

        # Build scalar payloads
        payloads = {}
        for node_id, ports in results.items():
            payloads[node_id] = {}
            for port_name, value in ports.items():
                payloads[node_id][port_name] = to_payload(value)

        # Capture reproducibility
        try:
            deps = resolve_dependency_versions([])
            repro = capture_run(graph, dependency_versions=deps)
            run_data["reproducibility"] = {
                "seeds": repro.seeds,
                "content_hashes": repro.content_hashes,
                "dependency_versions": repro.dependency_versions,
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
