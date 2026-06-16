"""
colonymind.nodes
~~~~~~~~~~~~~~~~~
The node-definition contract (Epic 1, Story 3) and its reference nodes.

Every node type conforms to :class:`NodeDefinition`, declaring its ports, typed
params (the serializable :mod:`~colonymind.nodes.spec` half), codegen template,
executor and optional type-inference (the Python-behaviour half).  The registry
and plugin architecture that discovers and indexes these definitions is Story 4
and will live alongside this package.
"""

from .contract import CodeFragment, NodeDefinition
from .spec import NodeSpec, ParamSpec, PortSpec, ValidationHints

__all__ = [
    "NodeDefinition",
    "CodeFragment",
    "NodeSpec",
    "PortSpec",
    "ParamSpec",
    "ValidationHints",
]
