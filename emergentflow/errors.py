"""
emergentflow.errors
~~~~~~~~~~~~~~~~~~~
Shared typed errors for cross-family concerns (model persistence, ...).

``ModelPersistenceError`` lives here rather than in a single family's errors
module so both ``ef.ml`` and ``ef.recommend`` can raise the *same* type without
one family importing the other -- the families are parallel seams (ADR 0021) and
must not depend on each other. Each family re-exports it from its own errors
module (e.g. ``emergentflow.ml.errors``) for discoverability.
"""

from __future__ import annotations

__all__ = ["ModelPersistenceError"]


class ModelPersistenceError(ValueError):
    """Raised when a model artifact cannot be saved or loaded.

    Covers version mismatch, wrong object type, and corruption. A
    :class:`ValueError` subclass so callers that catch the family error
    hierarchies (themselves ``ValueError`` subclasses) keep working.
    """
