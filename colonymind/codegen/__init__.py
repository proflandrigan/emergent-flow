"""
colonymind.codegen
~~~~~~~~~~~~~~~~~~~
The code-generation engine (Epic 2). Houses the whole-graph compiler and the
reference executor (Stories 5-6) and the shared graph-analysis plumbing both
rely on (Story 2): deterministic topological ordering, cycle detection, and the
input-wiring map.

Exposed publicly as the lazy ``cm.codegen`` namespace (see
``colonymind/__init__.py``). Top-level ``cm.compile_to_code`` / ``cm.execute``
entry points are reserved per ADR 0010 and land in Stories 5-6.
"""

from __future__ import annotations

from colonymind.codegen.context import CodegenContext, build_codegen_context
from colonymind.codegen.declarative import compile_declarative
from colonymind.codegen.errors import CardinalityError, CodegenError, CycleError, UnboundInputError
from colonymind.codegen.executor import execute
from colonymind.codegen.export import ExportResult, export_script
from colonymind.codegen.inference import (
    InferenceResult,
    ResolvedPortType,
    UnboundInput,
    infer_graph_types,
)
from colonymind.codegen.naming import NameMap, OutBinding, build_name_map
from colonymind.codegen.traversal import topological_sort
from colonymind.codegen.validation import (
    Diagnostic,
    Diagnostics,
    Severity,
    apply_type_compatibility,
    validate,
)
from colonymind.codegen.wiring import InputBinding, WiringMap, build_wiring_map

__all__ = [
    "CodegenError",
    "CycleError",
    "CardinalityError",
    "UnboundInputError",
    "topological_sort",
    "build_wiring_map",
    "WiringMap",
    "InputBinding",
    "build_name_map",
    "NameMap",
    "OutBinding",
    "CodegenContext",
    "build_codegen_context",
    "execute",
    "export_script",
    "ExportResult",
    "compile_declarative",
    "infer_graph_types",
    "InferenceResult",
    "ResolvedPortType",
    "UnboundInput",
    "validate",
    "apply_type_compatibility",
    "Diagnostics",
    "Diagnostic",
    "Severity",
]
