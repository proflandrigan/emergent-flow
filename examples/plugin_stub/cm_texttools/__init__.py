"""
cm_texttools
~~~~~~~~~~~~
Example out-of-core Colony Mind node plugin (Epic 1, Story 4).

Exposes a single transform node, ``ReverseText`` (catalog key
``text.reverse``), discovered by Colony Mind's registry via the
``colonymind.nodes`` entry point declared in ``pyproject.toml``.
"""

from .nodes import ReverseText

__all__ = ["ReverseText"]
