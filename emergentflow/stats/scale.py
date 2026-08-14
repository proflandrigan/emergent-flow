"""
emergentflow.stats.scale
~~~~~~~~~~~~~~~~~~~~~~~~~~
Pre-flight memory guards for stats operations that would otherwise materialize a dense D x D
matrix (``ef.stats.correlation``, ``ef.stats.co_missingness``).

The in-process synchronous executor means one node's allocation spike can OOM-kill the whole
``emergentflow serve`` process and every session. These operations' *output* is inherently a
D x D frame, so a D x D dense matrix cannot be avoided the way recommend KNN's can — the
guard refuses footprints above a configurable cap up front rather than letting the process
run out of memory. This mirrors ``emergentflow.recommend``'s ``RecommendationScaleError``
pre-flight guard (see ``docs/memory-and-scale-remediation.md``).
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_MAX_DENSE_FOOTPRINT_BYTES",
    "estimate_dense_square_bytes",
    "enforce_dense_square_guard",
]

from emergentflow.stats.errors import StatsScaleError

#: Default cap (bytes) for the estimated dense D x D footprint (2 GiB), matching the recommend
#: family default. Set ``max_footprint_bytes`` very large to effectively disable.
DEFAULT_MAX_DENSE_FOOTPRINT_BYTES = 2 * 1024**3


def estimate_dense_square_bytes(n: int) -> int:
    """Conservative estimate (bytes) of a dense n x n float64 array."""
    return int(n) * int(n) * 8


def enforce_dense_square_guard(n: int, max_footprint_bytes: int | None, what: str) -> None:
    """Raise :class:`StatsScaleError` if *n* columns would need a dense n x n footprint over the
    cap. *what* names the operation for the error message (e.g. ``"correlation"``). A
    ``max_footprint_bytes`` of ``None`` applies :data:`DEFAULT_MAX_DENSE_FOOTPRINT_BYTES`."""
    if n <= 0:
        return
    cap = (
        max_footprint_bytes
        if max_footprint_bytes is not None
        else DEFAULT_MAX_DENSE_FOOTPRINT_BYTES
    )
    estimate = estimate_dense_square_bytes(n)
    if estimate > int(cap):
        raise StatsScaleError(
            f"{what} on {n} columns would need ~{estimate / (1024**3):.1f} GiB (a dense "
            f"{n} x {n} pair matrix); this exceeds the configured cap "
            f"({estimate / (1024**3):.1f} > {cap / (1024**3):.1f} GiB). Refusing to protect the "
            f"shared server from OOM. Pass max_footprint_bytes higher (or very large) to allow "
            f"it, or restrict `columns`/reduce the column count."
        )
