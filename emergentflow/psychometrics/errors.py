"""
emergentflow.psychometrics.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the psychometrics family (issue #164 Gap 3).

Rooted at :class:`PsychometricsError` (a :class:`ValueError` subclass) so every
psychometrics-family failure is catchable with one except clause while staying compatible
with existing ``pytest.raises(ValueError)``-style tests, mirroring
``emergentflow.stats.errors.StatsError``.
"""

from __future__ import annotations

__all__ = [
    "PsychometricsError",
    "MissingOptionalDependencyError",
]


class PsychometricsError(ValueError):
    """Base class for all psychometrics-family errors."""


class MissingOptionalDependencyError(PsychometricsError):
    """Raised when a psychometrics op needs an optional dependency group that is not
    installed (e.g. ``emergentflow[psychometrics]`` for the IRT backend).

    The ``extra`` argument is the pip install target; the message tells the user exactly
    how to install it, so a base-install use never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
