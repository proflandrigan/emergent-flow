"""Colony Mind core SDK and graph intermediate representation (IR)."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import TYPE_CHECKING

from colonymind.api import (
    PUBLIC_OPS,
    InspectableContractError,
    assert_inspectable,
    is_inspectable,
    public_op,
)

__version__ = "0.2.0"

# Functional-pipeline namespaces (Epic 1, Story 8). Imported lazily so that
# ``import colonymind`` stays light — the heavy scientific stack (pandas,
# scikit-learn, ydata-profiling) is only pulled in when a family is first used.
_LAZY_FAMILIES = frozenset({"data", "clean", "stats", "ml", "reports"})

# Whole-graph code-generation engine namespace (Epic 2). Imported lazily like the
# functional families so a bare ``import colonymind`` stays light — the codegen
# package is only pulled in on first access to ``cm.codegen``.
_LAZY_NAMESPACES = _LAZY_FAMILIES | frozenset({"codegen"})

if TYPE_CHECKING:  # let type-checkers resolve cm.data, cm.codegen, ... statically
    from colonymind import clean, codegen, data, ml, reports, stats

__all__ = [
    "__version__",
    "PUBLIC_OPS",
    "InspectableContractError",
    "assert_inspectable",
    "is_inspectable",
    "public_op",
    "data",
    "clean",
    "stats",
    "ml",
    "reports",
    "codegen",
]


def __getattr__(name: str) -> ModuleType:
    """Lazily import a public family or engine namespace on first access."""
    if name in _LAZY_NAMESPACES:
        module = importlib.import_module(f"colonymind.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
