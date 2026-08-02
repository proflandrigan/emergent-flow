"""
emergentflow.validity.rules
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Validity rule implementations (Epic 17).

Each module registers its rules on the default registry by importing
``emergentflow.validity``'s ``@validity_rule`` decorator at module import time.
Importing this package fires registration of every in-tree rule; nothing else
needs to happen for a rule to participate in ``run_validity_checks``.
"""

from __future__ import annotations

from . import (
    leakage,  # noqa: F401  (registration is the side effect)
    metrics,  # noqa: F401  (registration is the side effect)
    skew,  # noqa: F401  (registration is the side effect)
    temporal,  # noqa: F401  (registration is the side effect)
)

__all__ = ["leakage", "metrics", "skew", "temporal"]
