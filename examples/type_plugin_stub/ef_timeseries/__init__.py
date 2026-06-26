"""
ef_timeseries
~~~~~~~~~~~~~
Example out-of-core Emergent Flow *type* plugin (Epic 3, Story 2).

Exposes a single new data-type token, ``TIMESERIES`` (token ``"TimeSeries"``, a
subtype of the core ``"DataFrame"`` token), discovered by Emergent Flow's type
registry via the ``emergentflow.types`` entry point declared in ``pyproject.toml``.
"""

from .types import TIMESERIES

__all__ = ["TIMESERIES"]
