"""
emergentflow.recommend.generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A pure generator mapping curated ``RecommenderSpec`` allow-list entries to catalog-entry dicts,
mirroring ``emergentflow.ml.generator.generate_estimator_catalog_entries``.

Turns the recommender registry into JSON-native data the canvas config panel renders with zero
per-algorithm UI code: no I/O, no global state, deterministic given the same input list. Every
entry's ``node_type`` is ``"recommend.fit"`` (the single node whose ``algorithm`` dropdown these
back).
"""

from __future__ import annotations

from typing import Any

from emergentflow.recommend.registry import RecommenderSpec

#: The node type whose ``algorithm`` param these recommender entries populate.
_RECOMMENDER_NODE_TYPE = "recommend.fit"


def _humanize(key: str) -> str:
    """``"popularity_segmented"`` -> ``"Popularity Segmented"``; ``"svd_cf"`` -> ``"Svd Cf"``."""
    return " ".join(word.capitalize() for word in key.split("_"))


def _json_native_default(default: Any) -> Any:
    """Normalize a curated param default to a JSON-native value.

    A few curated defaults are Python ``tuple``s (e.g. ``tfidf_similarity``'s ``ngram_range``,
    which its fitter passes straight to ``TfidfVectorizer`` and so keeps as a literal ``tuple``).
    JSON has no tuple type -- ``json.dumps`` serializes a tuple as an array, but round-tripping it
    back through ``json.loads`` yields a ``list``, making the in-memory catalog unequal to its own
    on-disk form (the ``test_export_ui_contracts_round_trips`` gate). Normalizing to ``list`` here
    keeps the catalog entry JSON-native by construction; the registry's own
    ``RecommenderParamSpec.default`` (used at fit time) is untouched and stays a ``tuple``.
    Mirrors ``emergentflow.ml.generator._json_native_default``.
    """
    return list(default) if isinstance(default, tuple) else default


def generate_recommender_catalog_entries(specs: list[RecommenderSpec]) -> list[dict[str, Any]]:
    """Map curated *specs* to JSON-native catalog-entry dicts, sorted by ``key``.

    Pure: output depends only on *specs*. Each entry has keys ``key``, ``node_type``, ``family``,
    ``label``, ``category``, ``description``, ``requires_extra``, and ``params`` (a list of
    ``{"name", "type", "default", "help", "choices", "required"}`` dicts, one per
    ``RecommenderParamSpec`` in ``spec.param_metadata``, in declared order). ``choices`` is the
    list form of ``RecommenderParamSpec.choices`` (or ``None``).
    """
    entries = []
    for spec in specs:
        entries.append(
            {
                "key": spec.key,
                "node_type": _RECOMMENDER_NODE_TYPE,
                "family": spec.family,
                "label": _humanize(spec.key),
                "category": _humanize(spec.family),
                "description": spec.description.strip(),
                "requires_extra": spec.requires_extra,
                "params": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "default": _json_native_default(p.default),
                        "help": p.help,
                        "choices": list(p.choices) if p.choices else None,
                        "required": p.required,
                    }
                    for p in spec.param_metadata
                ],
            }
        )
    return sorted(entries, key=lambda e: e["key"])
