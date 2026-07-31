"""
emergentflow.ml.errors
~~~~~~~~~~~~~~~~~~~~~~
Typed errors for the estimator adapter and allow-list registry (Epic 8, Story 2).

The hierarchy is rooted at :class:`MLAdapterError`, itself a :class:`ValueError`
subclass, so callers can catch every adapter failure with one except clause while
staying compatible with existing ``pytest.raises(ValueError)``-style tests.
"""

from __future__ import annotations

__all__ = [
    "MLAdapterError",
    "MissingOptionalDependencyError",
    "UnknownEstimatorError",
    "InvalidEstimatorParamsError",
    "ModelPersistenceError",
]


class MLAdapterError(ValueError):
    """Base class for all estimator-adapter / registry errors."""


class UnknownEstimatorError(MLAdapterError):
    """Raised when an estimator key is not present in the curated allow-list registry."""


class InvalidEstimatorParamsError(MLAdapterError):
    """Raised when a kwarg passed to an estimator is not in its accepted-kwargs allow-list."""


class MissingOptionalDependencyError(MLAdapterError):
    """Raised when an ml-family op needs an optional dependency group that is not installed."""

    def __init__(self, extra: str) -> None:
        self.extra = extra
        super().__init__(
            f"this feature requires the optional dependency group {extra!r}; "
            f"install it with `pip install {extra}`."
        )


class ModelPersistenceError(MLAdapterError):
    """Raised when a saved model cannot be loaded due to version mismatch or corruption."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
