"""
emergentflow.nodes.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~
The catalog-as-data export (Epic 6, Story 2).

Serializes the live node registry as a single versioned JSON artifact (ADR 0015) the
canvas palette + schema-driven config panels consume with no Python present. The artifact
carries its own ``catalog_version``, decoupled from ``Graph.schema_version`` (mirrors the
rules-as-data artifact, ADR 0012) so catalog growth does not force IR-wire-format migrations.

``export_catalog`` is the pure builder over a ``NodeRegistry``: no I/O, no global mutation,
deterministic ordering (nodes sorted by ``type`` via ``registry.specs()``).
"""

from __future__ import annotations

from typing import Any

import emergentflow.recommend.catalog  # noqa: F401  (registers the 15 curated algorithms)
from emergentflow.api import public_op
from emergentflow.data.warehouse.generator import generate_connector_catalog_entries
from emergentflow.ml.generator import generate_estimator_catalog_entries
from emergentflow.ml.registry import get_estimator_spec, known_estimator_keys
from emergentflow.nodes.registry import NodeRegistry
from emergentflow.nodes.registry import registry as default_registry
from emergentflow.recommend.generator import generate_recommender_catalog_entries
from emergentflow.recommend.registry import get_recommender_spec, known_recommender_keys
from emergentflow.viz.generator import generate_chart_catalog_entries
from emergentflow.viz.registry import get_chart_spec, known_chart_keys

#: Version of the catalog artifact *shape*. Bump on a breaking change to the artifact
#: structure (new/removed/renamed top-level or per-node fields). Distinct from
#: ``Graph.schema_version`` (IR wire format) and each node's contract ``version``.
CATALOG_VERSION = 5


@public_op(name="ef.export_catalog")
def export_catalog(registry: NodeRegistry = default_registry) -> dict[str, Any]:
    """Build the versioned node-catalog artifact from *registry*.

    Pure function of *registry*, the live estimator registry, the live chart registry, and the
    live recommender registry: no I/O, no global mutation. Nodes are emitted in ``type``-sorted
    order (``registry.specs()`` already sorts); the ``"estimators"`` list (Epic 8 prerequisite) is
    generated from the curated estimator allow-list via
    :func:`~emergentflow.ml.generator.generate_estimator_catalog_entries`, sorted by ``key``;
    the ``"charts"`` list (Epic 12, Story 8) is generated from the curated viz chart allow-list
    via :func:`~emergentflow.viz.generator.generate_chart_catalog_entries`, sorted by ``key``;
    the ``"connectors"`` list (Epic 13, Story 6) is generated from the curated warehouse
    connector allow-list via
    :func:`~emergentflow.data.warehouse.generator.generate_connector_catalog_entries`,
    sorted by ``dialect``; the ``"recommenders"`` list (Epic 15 prerequisite) is generated from
    the curated recommender algorithm allow-list via
    :func:`~emergentflow.recommend.generator.generate_recommender_catalog_entries`, sorted by
    ``key``.
    """
    estimator_specs = [get_estimator_spec(key) for key in known_estimator_keys()]
    chart_specs = [get_chart_spec(key) for key in known_chart_keys()]
    recommender_specs = [get_recommender_spec(key) for key in known_recommender_keys()]
    return {
        "catalog_version": CATALOG_VERSION,
        "nodes": [spec.model_dump(mode="json") for spec in registry.specs()],
        "estimators": generate_estimator_catalog_entries(estimator_specs),
        "charts": generate_chart_catalog_entries(chart_specs),
        "recommenders": generate_recommender_catalog_entries(recommender_specs),
        "connectors": generate_connector_catalog_entries(),
    }
