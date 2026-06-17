"""
colonymind.nodes
~~~~~~~~~~~~~~~~~
The node-definition contract (Epic 1, Story 3) and its reference nodes.

Every node type conforms to :class:`NodeDefinition`, declaring its ports, typed
params (the serializable :mod:`~colonymind.nodes.spec` half), codegen template,
executor and optional type-inference (the Python-behaviour half).  The registry
(``colonymind.nodes.registry``) indexes all known node types and is re-exported
here for convenient access.
"""

# Importing the reference-node package fires its ``@register`` decorators, so the
# default ``registry`` is populated with the in-tree nodes (``data.load_csv``,
# ``clean.impute_missing``) the moment ``colonymind.nodes`` is imported. Done last
# so ``registry``/``contract``/``spec`` are fully initialised before the examples
# import back from them. The import below is a deliberate import-for-side-effect;
# the lint suppression on it keeps it late (E402) and unused-but-intentional (F401).
from . import examples  # noqa: E402,F401
from .contract import CodeFragment, NodeDefinition
from .registry import (
    ENTRY_POINT_GROUP,
    NodeRegistry,
    by_family,
    by_port_type,
    discover,
    get,
    register,
    registry,
    validate,
)
from .spec import NodeSpec, ParamSpec, PortSpec, ValidationHints

__all__ = [
    "CodeFragment",
    "ENTRY_POINT_GROUP",
    "NodeDefinition",
    "NodeRegistry",
    "NodeSpec",
    "ParamSpec",
    "PortSpec",
    "ValidationHints",
    "by_family",
    "by_port_type",
    "discover",
    "get",
    "register",
    "registry",
    "validate",
]
