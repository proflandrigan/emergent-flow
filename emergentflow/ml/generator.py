"""
emergentflow.ml.generator
~~~~~~~~~~~~~~~~~~~~~~~~~~
A pure generator mapping curated ``EstimatorSpec`` allow-list entries to catalog-entry dicts
(Epic 8 prerequisite for Story 4/7).

Turns the estimator registry into JSON-native data the canvas palette can eventually render
with zero per-estimator UI code: no I/O, no global state, deterministic given the same input
list (mirrors the codegen pipeline's small-deterministic-pass convention). Descriptions come
from each sklearn class's docstring first line -- a minimal simplification; full curated,
hand-reviewed descriptions are a later enhancement (epic Story 7).
"""

from __future__ import annotations

import re
from typing import Any

from emergentflow.ml.registry import Archetype, EstimatorSpec

#: Maps each fixed adapter archetype (ADR 0016 subsection 3) to the node ``type`` that
#: consumes estimators of that archetype. Only "fit" has a node file today
#: (``ml.fit_estimator``); "fit_transform"/"cluster_detect" node types are separate,
#: later tasks (Story 5/6) -- their catalog entries are still generated here (the
#: generator is archetype-agnostic data plumbing) even though no node consumes them yet.
_ARCHETYPE_NODE_TYPE: dict[Archetype, str] = {
    "fit": "ml.fit_estimator",
    "fit_transform": "ml.fit_transform",
    "cluster_detect": "ml.cluster_detect",
}

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _humanize(token: str) -> str:
    """``"LogisticRegression"`` -> ``"Logistic Regression"``; CamelCase/underscore split."""
    spaced = _CAMEL_BOUNDARY.sub(" ", token.replace("_", " "))
    return " ".join(word.capitalize() for word in spaced.split())


def _category_from_import_path(import_path: str) -> str:
    """``"sklearn.linear_model.LogisticRegression"`` -> ``"Linear Model"``."""
    parts = import_path.split(".")
    module = parts[-2] if len(parts) >= 2 else parts[0]
    return _humanize(module)


def _first_doc_line(sklearn_class: type) -> str:
    """The first non-empty line of *sklearn_class*'s docstring, stripped. Empty if none."""
    doc = sklearn_class.__doc__ or ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _infer_param_type(default: Any) -> str:
    """Infer a catalog param ``type`` label from a kwarg's default value.

    ``bool`` is checked before ``int`` because ``bool`` is an ``int`` subclass in Python.
    """
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    if isinstance(default, str):
        return "str"
    return "any"


def generate_estimator_catalog_entries(specs: list[EstimatorSpec]) -> list[dict[str, Any]]:
    """Map curated *specs* to JSON-native catalog-entry dicts, sorted by ``key``.

    Pure: output depends only on *specs*. Each entry has keys ``key``, ``node_type``,
    ``archetype``, ``task``, ``label``, ``category``, ``description``, ``import_path``, and
    ``params`` (a list of ``{"name", "type", "default", "help"}`` dicts, one per curated
    ``accepted_kwargs`` entry, sorted by kwarg name).
    """
    entries = []
    for spec in specs:
        entries.append(
            {
                "key": spec.key,
                "node_type": _ARCHETYPE_NODE_TYPE[spec.archetype],
                "archetype": spec.archetype,
                "task": spec.task,
                "label": _humanize(spec.key),
                "category": _category_from_import_path(spec.import_path),
                "description": _first_doc_line(spec.sklearn_class),
                "import_path": spec.import_path,
                "params": [
                    {
                        "name": name,
                        "type": _infer_param_type(kwarg_spec.default),
                        "default": kwarg_spec.default,
                        "help": kwarg_spec.help,
                    }
                    for name, kwarg_spec in sorted(spec.accepted_kwargs.items())
                ],
            }
        )
    return sorted(entries, key=lambda e: e["key"])
