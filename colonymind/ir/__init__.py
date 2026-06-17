"""Colony Mind graph intermediate representation (IR) models."""

# Import order matters: graph.py defines Graph and resolves the Node<->Graph
# forward reference via model_rebuild(), so importing the package fully defines
# every model regardless of which submodule a caller imports first.
from . import common, edge, graph, node, params, port, serialize  # noqa: F401,E402
from .common import (  # noqa: F401
    ArtifactRef,
    Cardinality,
    Direction,
    IRId,
    IRModel,
    Paradigm,
    new_id,
)
from .edge import Edge, PortRef  # noqa: F401
from .graph import CURRENT_SCHEMA_VERSION, Graph  # noqa: F401
from .node import Node, Position  # noqa: F401
from .params import Param, ParamValue  # noqa: F401
from .port import Port  # noqa: F401
from .serialize import (  # noqa: F401
    GraphDeserializationError,
    GraphSerializationError,
    SchemaVersionError,
    deserialize_graph,
    load_graph,
    save_graph,
    serialize_graph,
)
