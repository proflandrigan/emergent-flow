"""``colonymind`` console entry point (ADR 0013 Decision 2, §A6).

Subcommands:
- ``colonymind serve`` -- boot the thin local canvas server (in-process ``cm.*``).
- ``colonymind lab``   -- alias for ``serve`` (the JupyterLab-style launch verb).

Kept dependency-light: the server (and stdlib ``http.server``) is imported lazily
inside ``main`` so ``import colonymind.cli`` stays cheap.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colonymind",
        description="Colony Mind - local canvas + open-source data/ML SDK.",
    )
    sub = parser.add_subparsers(dest="command")
    for name in ("serve", "lab"):
        p = sub.add_parser(name, help="Boot the local canvas server (in-process cm.*).")
        p.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
        p.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in ("serve", "lab"):
        from colonymind.server import serve

        serve(host=args.host, port=args.port)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
