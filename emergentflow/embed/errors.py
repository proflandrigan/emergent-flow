"""
emergentflow.embed.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the embed family.

Rooted at :class:`EmbedError` (a :class:`ValueError` subclass) so every embed-family failure
is catchable with one except clause, mirroring ``emergentflow.explain.errors.ExplainError``.
"""

from __future__ import annotations

__all__ = [
    "EmbedError",
    "MissingClientError",
    "MissingOptionalDependencyError",
]


class EmbedError(ValueError):
    """Base class for all embed-family errors."""


class MissingClientError(EmbedError):
    """Raised by the API embedding path when no client was injected."""


class MissingOptionalDependencyError(EmbedError):
    """Raised when the local backend needs ``emergentflow[embed]`` and it is not installed.

    The message tells the user exactly how to install it, so a base-install use
    of the local backend never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
