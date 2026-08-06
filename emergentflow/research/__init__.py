"""
emergentflow.research
~~~~~~~~~~~~~~~~~~~~~
Reports, lineage, reproducibility, and data-quality ops for Emergent Flow (Epic 16).

Currently home to ``trace_lineage``/``build_report``/``capture_run``/``check_data_quality``; the
``assert_data`` node lands in a later task.
"""

from __future__ import annotations

from emergentflow.research.errors import (
    DataQualityError,
    MissingOptionalDependencyError,
    ResearchError,
    UnknownNodeError,
)
from emergentflow.research.lineage import (
    ColumnLineage,
    ColumnLineageEdge,
    ColumnLineageNode,
    ColumnRole,
    Lineage,
    LineageEdge,
    LineageNode,
    trace_column_impact,
    trace_column_lineage,
    trace_lineage,
)
from emergentflow.research.quality import EXPECTATION_TYPES, check_data_quality
from emergentflow.research.report import (
    Report,
    ReportMeta,
    Section,
    build_report,
    section_from_value,
    sections_from_values,
)
from emergentflow.research.reproducibility import (
    SEED_PARAM_NAMES,
    ReproducibilityCapture,
    capture_run,
    resolve_dependency_versions,
)

__all__ = [
    "DataQualityError",
    "EXPECTATION_TYPES",
    "Lineage",
    "LineageEdge",
    "LineageNode",
    "MissingOptionalDependencyError",
    "Report",
    "ReportMeta",
    "ReproducibilityCapture",
    "ResearchError",
    "SEED_PARAM_NAMES",
    "Section",
    "UnknownNodeError",
    "build_report",
    "capture_run",
    "check_data_quality",
    "resolve_dependency_versions",
    "section_from_value",
    "sections_from_values",
    "trace_lineage",
    "trace_column_impact",
    "trace_column_lineage",
    "ColumnLineage",
    "ColumnLineageEdge",
    "ColumnLineageNode",
    "ColumnRole",
]
