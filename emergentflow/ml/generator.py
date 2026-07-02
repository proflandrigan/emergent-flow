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

#: Splits before a lowercase/digit -> uppercase transition (``"Logistic|Regression"``) and
#: before the last capital of an acronym run when followed by a new word (``"Gaussian|NB"``,
#: ``"Linear|SVC"``) -- but never inside a bare acronym (``"SVC"``, ``"LDA"`` stay whole).
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

#: Lowercase sklearn module segments that are acronyms, not words -- ``_humanize`` would
#: otherwise title-case them into nonsense (``"svm"`` -> ``"Svm"`` instead of ``"SVM"``).
_ACRONYMS = frozenset({"svm"})


def _humanize(token: str) -> str:
    """``"LogisticRegression"`` -> ``"Logistic Regression"``; CamelCase/underscore split.

    Preserves existing acronym runs (``"GaussianNB"`` -> ``"Gaussian NB"``, not ``"Gaussian N
    B"``) and upper-cases known lowercase acronyms (``"svm"`` -> ``"SVM"``).
    """
    spaced = _CAMEL_BOUNDARY.sub(" ", token.replace("_", " "))
    words = []
    for word in spaced.split():
        if word.isupper() or word.lower() in _ACRONYMS:
            words.append(word.upper())
        else:
            words.append(word.capitalize())
    return " ".join(words)


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


def _json_native_default(default: Any) -> Any:
    """Normalize a curated kwarg default to a JSON-native value.

    A few curated defaults are Python ``tuple``s (e.g. ``MinMaxScaler``'s ``feature_range``,
    which sklearn's own parameter validation requires to be a literal ``tuple`` at estimator-
    construction time, not a ``list``). JSON has no tuple type -- ``json.dumps`` already
    serializes a tuple as an array, but round-tripping it back through ``json.loads`` yields a
    ``list``, not a ``tuple``, which would make the exported catalog dict unequal to itself
    across a JSON round trip. Normalizing to a ``list`` here keeps the catalog entry JSON-native
    by construction; the registry's own ``KwargSpec.default`` (used to construct the live
    estimator) is untouched and stays a ``tuple``.
    """
    return list(default) if isinstance(default, tuple) else default


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
                        "default": _json_native_default(kwarg_spec.default),
                        "help": kwarg_spec.help,
                    }
                    for name, kwarg_spec in sorted(spec.accepted_kwargs.items())
                ],
            }
        )
    return sorted(entries, key=lambda e: e["key"])
