"""
ef_timeseries.types
~~~~~~~~~~~~~~~~~~~~
Out-of-core *type* plugin for Emergent Flow (Epic 3, Story 2).

Contributes a single new data-type token, ``TimeSeries``, declared as a subtype of
the core ``DataFrame`` token. The entry point in this package's ``pyproject.toml``
under the ``emergentflow.types`` group is the *only* integration surface: core's
``TypeRegistry.discover()`` loads ``TIMESERIES`` and registers it with no
``@register`` decorator and zero changes to ``emergentflow`` core.

Unlike the in-core ``emergentflow.types.catalog`` module, this plugin does NOT
self-register on import — registration happens via the entry point + ``discover()``.
"""

from __future__ import annotations

from emergentflow.types.registry import TypeDef

TIMESERIES = TypeDef(
    token="TimeSeries",
    description="A time-indexed tabular dataset; a subtype of DataFrame.",
    supertypes=("DataFrame",),
)
