"""
colonymind.types
~~~~~~~~~~~~~~~~~
The type-token system (Epic 3, Story 2).

A nominal type system over the IR's ``Port.data_type`` tokens: a catalog of known
type tokens plus an optional ``(subtype, supertype)`` relation, with ``"any"`` as
the explicit top/wildcard type (ADR 0011). The registry
(:mod:`colonymind.types.registry`) is the authoritative catalog and serializes to
plain JSON (:meth:`~colonymind.types.registry.TypeRegistry.to_dict`) so the rules
can later ship to the frontend (ADR 0012). The built-in catalog
(:mod:`colonymind.types.catalog`) registers the core tokens at import time.
"""

from .registry import (
    ENTRY_POINT_GROUP,
    TOP_TYPE,
    TypeDef,
    TypeRegistry,
    discover_types,
    register_type,
    registry,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "TOP_TYPE",
    "TypeDef",
    "TypeRegistry",
    "discover_types",
    "register_type",
    "registry",
]

# Importing the built-in catalog registers the core data-type tokens (DataFrame,
# ClassifierResult, AnovaResult, HTML, Tensor) into the default ``registry`` the
# moment ``colonymind.types`` is imported — the same import-for-side-effect pattern
# the node package uses for its reference nodes. Kept last so ``registry`` is fully
# initialised before the catalog imports back from it. The lint suppression marks it
# as not-at-top (E402) and unused-but-intentional (F401).
from . import catalog  # noqa: E402, F401
