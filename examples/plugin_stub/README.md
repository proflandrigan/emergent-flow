# cm-texttools — Example Colony Mind node plugin

This package is a minimal, self-contained demonstration of **out-of-core node
discovery**: a node that lives in a *separate* Python package, completely
outside `colonymind` core, is automatically picked up by the Colony Mind node
registry with **zero changes to core**.

## The key idea

The entire integration surface is one line in this package's `pyproject.toml`:

```toml
[project.entry-points."colonymind.nodes"]
text_reverse = "cm_texttools.nodes:ReverseText"
```

When this package is pip-installed, Python's packaging metadata records the
entry point.  When `colonymind.nodes.discover()` is called, it enumerates all
installed entry points in the `colonymind.nodes` group, loads each one, and
registers it in the node catalog — no fork, no core edit, no import-time side
effects required.

## What's in the box

- **`cm_texttools/nodes.py`** — a single transform node, `text.reverse`, that
  reverses a `Text` string.  Dependency-free (pure Python).  Conforms to
  `NodeDefinition` exactly like in-tree reference nodes (`load_csv.py` is the
  pattern).  No `@register` decorator — discovery happens via the entry point.
- **`cm_texttools/__init__.py`** — re-exports `ReverseText`.
- **`pyproject.toml`** — the installable package with the entry-point declaration.

## How to try it

```bash
# Install the stub into the same environment as colonymind:
pip install -e examples/plugin_stub

# Verify it loads cleanly via the entry-point path:
python -c "
from colonymind.nodes import registry, discover
problems = discover()
print('problems:', problems)          # should be []
print('text.reverse in registry:', 'text.reverse' in registry)  # True
"
```

`discover()` returns a list of problem strings (empty on success) and is the
function Colony Mind core calls to pull in all installed plugins.  A non-empty
list means a plugin failed to load; it is recorded but never raises, so other
plugins continue loading.

## ADR-0002 compliance

Both `ReverseText.execute` and the code emitted by `ReverseText.codegen` call
the shared helper `reverse_text(value)`.  They are equivalent by construction —
running the emitted snippet in a scope with `text="abc"` produces the same
`text` value as calling `execute` directly.
