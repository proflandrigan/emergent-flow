"""
ef_texttools
~~~~~~~~~~~~
Example out-of-core Emergent Flow node plugin (Epic 1, Story 4).

Exposes a single transform node, ``ReverseText`` (catalog key
``text.reverse``), discovered by Emergent Flow's registry via the
``emergentflow.nodes`` entry point declared in ``pyproject.toml``.
"""

from .nodes import ReverseText

__all__ = ["ReverseText"]
