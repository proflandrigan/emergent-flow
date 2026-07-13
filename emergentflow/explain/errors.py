"""
emergentflow.explain.errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the explain family (ADR 0020).

Rooted at :class:`ExplainError` (a :class:`ValueError` subclass) so every explain-family failure
is catchable with one except clause while staying compatible with existing
``pytest.raises(ValueError)``-style tests, mirroring ``emergentflow.stats.errors.StatsError``.
"""

from __future__ import annotations

__all__ = [
    "ExplainError",
    "UnsupportedModelError",
    "MissingOptionalDependencyError",
]


class ExplainError(ValueError):
    """Base class for all explain-family errors."""


class UnsupportedModelError(ExplainError):
    """Raised when a node is given a model archetype/task it does not support.

    For example: a ``FittedTransformer`` or a ``cluster_detect``-archetype ``FittedModel``
    passed to a SHAP/error-analysis node (which requires a supervised ``fit``-archetype
    ``FittedModel``), or a multiclass model passed to a binary-only node (calibration, ROC/PR).
    """


class MissingOptionalDependencyError(ExplainError):
    """Raised when a node needs the optional ``emergentflow[explain]`` dependency group
    (shap) and it is not installed.

    The ``extra`` argument is the pip install target (always ``"emergentflow[explain]"`` for
    this family); the message tells the user exactly how to install it, so a base-install use
    of a SHAP-backed node never surfaces an opaque ``ImportError``.
    """

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )
