"""``emergentflow`` console entry point (ADR 0013 Decision 2, §A6).

Subcommands:
- ``emergentflow serve`` -- boot the thin local canvas server (in-process ``ef.*``).
- ``emergentflow lab``   -- alias for ``serve`` (the JupyterLab-style launch verb).

Kept dependency-light: the server (and stdlib ``http.server``) is imported lazily
inside ``main`` so ``import emergentflow.cli`` stays cheap.
"""

from __future__ import annotations

import argparse
import sys
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
        )
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
