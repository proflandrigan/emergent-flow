"""
emergentflow.codegen.naming
~~~~~~~~~~~~~~~~~~~~~~~~~~
Deterministic, readable variable naming for the code-generation engine
(Epic 2, Story 3).

This module starts with pure string-level helpers: turning arbitrary node/port
labels into ASCII snake_case fragments, then into valid, non-shadowing Python
identifiers. On top of those helpers, `build_name_map` walks a whole graph and
assigns one stable Python variable name to every OUT port, returned as a
serializable `NameMap`.
"""

from __future__ import annotations

import hashlib
import keyword
import unicodedata
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from emergentflow.api import public_op
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node

_AVOID_BUILTINS = frozenset(
    {
        "id",
        "type",
        "list",
        "dict",
        "set",
        "str",
        "int",
        "float",
        "bool",
        "sum",
        "min",
        "max",
        "filter",
        "map",
        "input",
        "format",
        "object",
        "bytes",
        "tuple",
        "range",
        "len",
        "open",
        "vars",
        "hash",
        "next",
        "iter",
        "sorted",
        "print",
    }
)


def _slugify(text: str) -> str:
    """Reduce arbitrary *text* to an ASCII snake_case fragment.

    Unicode is transliterated via NFKD normalization and non-ASCII remainder is
    dropped. The result is lowercased and every run of non-alphanumeric
    characters collapses to a single underscore, with leading/trailing
    underscores stripped. The slug MAY be empty and MAY start with a digit —
    callers needing a valid identifier should pass the result through
    `_sanitize_identifier`.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    chars: list[str] = []
    prev_was_underscore = False
    for ch in ascii_text.lower():
        if ch.isalnum():
            chars.append(ch)
            prev_was_underscore = False
        elif not prev_was_underscore:
            chars.append("_")
            prev_was_underscore = True
    return "".join(chars).strip("_")


def _sanitize_identifier(slug: str) -> str:
    """Turn *slug* into a valid, non-shadowing Python identifier.

    An empty slug is returned as-is (the caller supplies a fallback). A slug
    starting with a digit is prefixed with an underscore. A slug that is a
    keyword, a soft keyword, or a common builtin name (see `_AVOID_BUILTINS`)
    is suffixed with an underscore to avoid shadowing it.
    """
    if not slug:
        return ""
    if slug[0].isdigit():
        slug = f"_{slug}"
    if keyword.iskeyword(slug) or keyword.issoftkeyword(slug) or slug in _AVOID_BUILTINS:
        slug = f"{slug}_"
    return slug


class OutBinding(BaseModel):
    """A single OUT port's assigned Python variable name."""

    node_id: str
    port_id: str
    var_name: str


class NameMap(BaseModel):
    """The whole-graph OUT-port naming map: one `OutBinding` per OUT port.

    The serializable surface is the `bindings` list; fast lookup is served by a
    private index rebuilt automatically after construction or deserialization.
    """

    bindings: list[OutBinding] = Field(default_factory=list)

    _by_port: dict[tuple[str, str], str] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Build the (node_id, port_id) -> var_name lookup index from `bindings`."""
        self._by_port = {(b.node_id, b.port_id): b.var_name for b in self.bindings}

    def var_for(self, node_id: str, port_id: str) -> str:
        """Return the Python variable name bound to the given OUT port.

        Raises `KeyError` if the (node_id, port_id) is not a known OUT port in
        this map.
        """
        key = (node_id, port_id)
        if key not in self._by_port:
            raise KeyError(f"No OUT port {port_id!r} on node {node_id!r} in this name map.")
        return self._by_port[key]


def _hash_suffix(node_id: str, port_id: str, length: int) -> str:
    """Short, stable hex suffix for disambiguating a colliding (node, port).

    Uses `hashlib.blake2s` (never the builtin `hash()`, which is salted and
    non-deterministic across runs) over `f"{node_id}:{port_id}"` so two OUT
    ports on the *same* node that slug to the same candidate still disambiguate.
    """
    digest = hashlib.blake2s(f"{node_id}:{port_id}".encode(), digest_size=8)
    return digest.hexdigest()[:length]


# Names the compiled `main()` reserves for its own keyword arguments (`clients`/`client`) and
# preamble locals (`warehouse`/`http`/`client`): a graph param that sanitized to one of these
# would either duplicate a signature parameter (SyntaxError) or be shadowed by the preamble
# assignment before any node runs, silently discarding the override (issue #116).
_MAIN_RESERVED_NAMES = frozenset({"clients", "client", "warehouse", "http"})


def _base_name(node: Node) -> str:
    """Readable base name for *node*: its label, falling back to its type."""
    label = (node.label or "").strip()
    base = _sanitize_identifier(_slugify(label)) if label else ""
    if not base:
        base = _sanitize_identifier(_slugify(node.type))
    if not base:
        base = "node"
    return base


@public_op(name="ef.codegen.build_name_map")
def build_name_map(graph: Graph) -> NameMap:
    """Assign a stable, readable Python variable name to every OUT port.

    Every OUT port's candidate name is always `f"{node_base}_{port_slug}"`
    (the port name is always suffixed, even on single-output nodes). When more
    than one OUT port produces the same candidate, every colliding entry is
    disambiguated by appending a short, stable `hashlib.blake2s`-derived hex
    suffix of the (node_id, port_id) pair — never the builtin `hash()`, which
    is salted and would break the determinism golden tests rely on. The suffix
    length starts at 4 and grows (capped at 16, the full 8-byte digest) until
    every colliding name is distinct from every other generated name.

    Iteration order is `sorted(graph.nodes.values(), key=node id)` then
    declared port order — never insertion order — so the same graph always
    yields the same map.
    """
    # Pass 1: compute every OUT port's collision candidate name, in
    # deterministic (node id, then declared port order) order.
    entries: list[tuple[str, str, str]] = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        node_base = _base_name(node)
        for port in node.ports:
            if port.direction != Direction.OUT:
                continue
            port_slug = _sanitize_identifier(_slugify(port.name)) or "out"
            candidate = f"{node_base}_{port_slug}"
            entries.append((node.id, port.id, candidate))

    # Pass 2: find which candidates collide (shared by more than one OUT port).
    counts = Counter(candidate for _, _, candidate in entries)
    bare_names = {candidate for candidate in counts if counts[candidate] == 1}

    # Pass 3: grow the hash-suffix length until every colliding entry's
    # suffixed name is unique among itself and disjoint from the bare names.
    # Deterministic and guaranteed to terminate: capped at 16 (the full
    # 8-byte blake2s digest), at which point distinct (node_id, port_id)
    # pairs are effectively guaranteed not to collide.
    length = 4
    while length <= 16:
        suffixed = [
            f"{candidate}_{_hash_suffix(node_id, port_id, length)}"
            for node_id, port_id, candidate in entries
            if counts[candidate] > 1
        ]
        if len(suffixed) == len(set(suffixed)) and bare_names.isdisjoint(suffixed):
            break
        length += 1

    # Pass 4: assemble bindings in entries order.
    bindings: list[OutBinding] = []
    for node_id, port_id, candidate in entries:
        if counts[candidate] == 1:
            var_name = candidate
        else:
            var_name = f"{candidate}_{_hash_suffix(node_id, port_id, length)}"
        bindings.append(OutBinding(node_id=node_id, port_id=port_id, var_name=var_name))

    return NameMap(bindings=bindings)


def build_graph_param_names(graph: Graph, name_map: NameMap) -> dict[str, str]:
    """Assign a stable, collision-free Python variable name to each graph-level param.

    The compiled ``main()`` takes one keyword argument per graph param, named from the param's
    name (sanitized to a valid identifier). A candidate that collides with an OUT-port variable
    already allocated by *name_map*, with one of the names the compiled ``main()`` reserves for
    its own signature/locals (``clients``, ``client``, ``warehouse``, ``http``), or with another
    graph param's sanitized form, is disambiguated with the same stable blake2s hash suffix
    ``build_name_map`` uses. Graph params are processed in sorted param-name order for
    determinism.
    """
    taken = {b.var_name for b in name_map.bindings} | _MAIN_RESERVED_NAMES
    names: dict[str, str] = {}
    for pname in sorted(graph.params):
        base = _sanitize_identifier(_slugify(pname)) or "param"
        candidate = base
        if candidate in taken:
            length = 4
            while candidate in taken and length <= 16:
                candidate = f"{base}_{_hash_suffix(pname, 'gparam', length)}"
                length += 1
        names[pname] = candidate
        taken.add(candidate)
    return names
