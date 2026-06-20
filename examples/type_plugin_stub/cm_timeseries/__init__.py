"""
cm_timeseries
~~~~~~~~~~~~~
Example out-of-core Colony Mind *type* plugin (Epic 3, Story 2).

Exposes a single new data-type token, ``TIMESERIES`` (token ``"TimeSeries"``, a
subtype of the core ``"DataFrame"`` token), discovered by Colony Mind's type
registry via the ``colonymind.types`` entry point declared in ``pyproject.toml``.
"""

from .types import TIMESERIES

__all__ = ["TIMESERIES"]
