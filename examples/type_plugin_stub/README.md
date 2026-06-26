# ef-timeseries — Example Emergent Flow type plugin

This package is a minimal, self-contained demonstration of **out-of-core type
discovery**: a new data-type token that lives in a *separate* Python package,
completely outside `emergentflow` core, is automatically picked up by the Colony
Mind **type** registry with **zero changes to core**.

It is the type-system counterpart of the node plugin in `examples/plugin_stub`
(`ef-texttools`): that one contributes a *node*; this one contributes a *type token*.

## The key idea

The entire integration surface is one line in this package's `pyproject.toml`:

```toml
[project.entry-points."emergentflow.types"]
time_series = "ef_timeseries.types:TIMESERIES"
```

When this package is pip-installed, Python's packaging metadata records the entry
point. When `emergentflow.types.discover_types()` (or `registry.discover()`) is
called, it enumerates all installed entry points in the `emergentflow.types` group,
loads each one, and registers the resulting `TypeDef` in the type catalog — no
fork, no core edit, no import-time side effects required.

## What's in the box

- **`ef_timeseries/types.py`** — a single `TypeDef` instance, `TIMESERIES`, declaring
  the token `TimeSeries` as a **subtype of the core `DataFrame` token**. Importing it
  has no side effects; registration happens via discovery, not at import time.
- **`ef_timeseries/__init__.py`** — re-exports `TIMESERIES`.
- **`pyproject.toml`** — the installable package with the entry-point declaration.

## How to try it

```bash
# Install the stub into the same environment as emergentflow:
pip install -e examples/type_plugin_stub

# Verify it loads cleanly via the entry-point path:
python -c "
from emergentflow.types import registry, discover_types
problems = discover_types()
print('problems:', problems)                       # should be []
print('TimeSeries registered:', 'TimeSeries' in registry)        # True
print('TimeSeries <: DataFrame:', registry.is_subtype('TimeSeries', 'DataFrame'))  # True
print('TimeSeries <: any:', registry.is_subtype('TimeSeries', 'any'))              # True
"
```

`discover_types()` returns a list of problem strings (empty on success) and is the
function Emergent Flow core calls to pull in all installed type plugins. A non-empty
list means a plugin failed to load; it is recorded but never raises, so other
plugins continue loading.

## Why a subtype edge?

Declaring `TimeSeries` a subtype of `DataFrame` means a node producing a `TimeSeries`
output may feed any input that expects a `DataFrame` (per the compatibility rules,
Epic 3 Story 3). This is the smallest meaningful demonstration of the optional subtype
relation that the nominal type system (ADR 0011) supports.
