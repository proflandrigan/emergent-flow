"""Shared pytest fixtures.

Test isolation for the global node registry. A handful of tests exercise the module-level
``@register`` decorator, which mutates the shared default :data:`emergentflow.nodes.registry`
singleton (see ``test_registry.py``). Without cleanup those dummy ``x.*`` node types leak into
the singleton for the rest of the session, which then surfaces anywhere that reads the live
catalog -- e.g. ``server.service.get_catalog`` and the ``ui/src/generated/catalog.json``
staleness check (``test_ui_contracts.py``). This autouse fixture snapshots the registry's
contents before each test and restores them afterwards, so registrations made during one test
never bleed into another. Tests that build their own ``NodeRegistry()`` are unaffected.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from emergentflow.nodes import registry


@pytest.fixture(autouse=True)
def _isolate_node_registry() -> Iterator[None]:
    saved = dict(registry._defs)
    try:
        yield
    finally:
        registry._defs.clear()
        registry._defs.update(saved)
