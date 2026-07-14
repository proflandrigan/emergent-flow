"""Emergent Flow core SDK and graph intermediate representation (IR)."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import TYPE_CHECKING, Any

from emergentflow.api import (
    PUBLIC_OPS,
    InspectableContractError,
    assert_inspectable,
    is_inspectable,
    public_op,
)

__version__ = "0.2.2"

# Functional-pipeline namespaces (Epic 1, Story 8). Imported lazily so that
# ``import emergentflow`` stays light — the heavy scientific stack (pandas,
# scikit-learn, ydata-profiling) is only pulled in when a family is first used.
_LAZY_FAMILIES = frozenset(
    {
        "data",
        "clean",
        "stats",
        "ml",
        "reports",
        "script",
        "llm",
        "eval",
        "explain",
        "viz",
        "timeseries",
    }
)

# Whole-graph code-generation engine namespace (Epic 2). Imported lazily like the
# functional families so a bare ``import emergentflow`` stays light — the codegen
# package is only pulled in on first access to ``ef.codegen``.
_LAZY_NAMESPACES = _LAZY_FAMILIES | frozenset({"codegen"})

# Top-level function entry points the codegen engine exposes (ADR 0010).
# Unlike _LAZY_NAMESPACES (which resolve to a module object), each of these
# resolves to a specific callable, imported from the codegen package only
# on first access so a bare ``import emergentflow`` stays light.
_LAZY_ENTRY_POINTS = {
    "compile_to_code": ("emergentflow.codegen.compiler", "compile_to_code"),
    "execute": ("emergentflow.codegen.executor", "execute"),
    "export_script": ("emergentflow.codegen.export", "export_script"),
    "validate": ("emergentflow.codegen.validation", "validate"),
    "apply_type_compatibility": ("emergentflow.codegen.validation", "apply_type_compatibility"),
    "build_rules_artifact": ("emergentflow.types.rules_artifact", "build_rules_artifact"),
    "diagnostics_json_schema": (
        "emergentflow.codegen.diagnostics_schema",
        "diagnostics_json_schema",
    ),
    "export_catalog": ("emergentflow.nodes.catalog", "export_catalog"),
}

if TYPE_CHECKING:  # let type-checkers resolve ef.data, ef.codegen, ... statically
    from emergentflow import (
        clean,
        codegen,
        data,
        eval,
        explain,
        llm,
        ml,
        reports,
        script,
        stats,
        timeseries,
        viz,
    )
    from emergentflow.codegen.compiler import compile_to_code
    from emergentflow.codegen.diagnostics_schema import diagnostics_json_schema
    from emergentflow.codegen.executor import execute
    from emergentflow.codegen.export import export_script
    from emergentflow.codegen.validation import apply_type_compatibility, validate
    from emergentflow.nodes.catalog import export_catalog
    from emergentflow.types.rules_artifact import build_rules_artifact

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
    "timeseries",
    "ml",
    "reports",
    "script",
    "llm",
    "eval",
    "explain",
    "viz",
    "codegen",
    "compile_to_code",
    "execute",
    "export_script",
    "validate",
    "apply_type_compatibility",
    "build_rules_artifact",
    "diagnostics_json_schema",
    "export_catalog",
]


def __getattr__(name: str) -> ModuleType | Any:
    """Lazily import a public family, engine namespace, or entry point on first access."""
    if name in _LAZY_NAMESPACES:
        module = importlib.import_module(f"emergentflow.{name}")
        globals()[name] = module
        return module
    if name in _LAZY_ENTRY_POINTS:
        module_path, attr_name = _LAZY_ENTRY_POINTS[name]
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
