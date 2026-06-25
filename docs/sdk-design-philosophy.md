# SDK Design Philosophy

> These conventions are cheap to adopt now and very expensive to retrofit, so they are
> enforced as acceptance criteria for **every** wrapper in the Emergent Flow SDK (Epic 1,
> Story 7). This document states the rules and the machinery that enforces them. For the
> concrete naming/signature/return mechanics, see
> [Public API Conventions](./public-api-conventions.md).

## The four rules

### 1. Thin wrappers

Every public operation is a **thin, direct** wrapper over a trusted underlying library.
The SDK adds convenience, schema alignment, and a consistent return shape — it does **not**
reimplement the library's logic. If a wrapper grows substantial bespoke logic, that is a
signal the work belongs in the underlying library or a dedicated node, not in the wrapper.

### 2. Deterministic

Given the same inputs, an operation must produce the same output. Any randomness must be
seeded explicitly through a parameter (e.g. `random_seed`), never drawn from hidden global
state. Determinism is what lets the IR's two pure functions — `compile_to_code(ir)` and
`execute(ir)` — stay equivalent (ADR 0002), and what makes results cacheable by content
hash (ADR 0004).

### 3. Pure functions where possible

Operations should be pure: no hidden global state, no side effects beyond what the function
name implies, and **no mutation of input arguments** (return new objects instead). The only
I/O an operation performs is what its signature declares (a `load_*` reads a file; a
transform does not). Purity keeps the graph the single source of truth (ADR 0001).

### 4. Serializable + inspectable returns

Every operation must return a **serializable and inspectable** object. Concretely, one of:

- a **Pydantic model**,
- a **dataclass** instance,
- a **tidy DataFrame**, or
- a **JSON-native value** (dict with string keys, list, str, int, float, bool, None),
  composed recursively.

Opaque, library-internal handles are **forbidden** as the sole return: they cannot be
serialized into the IR's artifact store (ADR 0004) nor inspected by users without knowing
the wrapped library's internals.

## Library selection follows from rule 4

"Returns inspectable structured data" is a **selection criterion for every wrapped
library**, not an afterthought. When two libraries cover the same capability, prefer the
one whose outputs are already structured and serializable. This is precisely why
[statsmodels](https://www.statsmodels.org/) is the chosen statistics backend: its
`anova_lm` and related routines return clean, tidy `DataFrame`s rather than opaque result
objects, so a thin wrapper satisfies rule 4 with no translation layer. A library that only emits opaque handles forces the
wrapper to do reverse-engineering work — a violation of rule 1 (thin) as well.

## How the rules are enforced

The rules are not merely documented — they are checked at runtime and in CI by
[`emergentflow/api.py`](../emergentflow/api.py):

| Tool | What it does |
| --- | --- |
| `is_inspectable(obj)` | Predicate: is a value a serializable + inspectable result? |
| `assert_inspectable(obj)` | Raises `InspectableContractError` for an opaque return. |
| `@public_op` | Decorate a wrapper: registers it in `PUBLIC_OPS` and validates its return on **every call**. |
| `PUBLIC_OPS` | The registry a test sweep iterates to enforce the contract catalog-wide. |

All four are re-exported from the package root:

```python
import emergentflow as ef

@ef.public_op
def my_op(df, *, alpha: float = 0.05):
    ...  # returns a Pydantic model / dataclass / DataFrame / JSON-native value
```

`tests/test_api_conventions.py` is the lint/test check Story 7 calls for: it proves the
contract accepts the sanctioned shapes and **flags** opaque objects, generators, file
handles, and raw bytes. As Story 8 adds the first real wrappers (`ef.data`, `ef.clean`,
`ef.stats`, `ef.ml`, `ef.reports`), each one decorated with `@public_op` inherits this
enforcement for free.

## Related documentation

- [Public API Conventions](./public-api-conventions.md) — naming, signatures, return-object mechanics.
- [Package Layout](./package-layout.md) — the namespace structure these wrappers live in.
- [ADR 0002](./adr/0002-execute-the-ir-not-the-string.md) — execute the IR, not a string (determinism).
- [ADR 0004](./adr/0004-storage-tiering.md) — artifact storage (why returns must be serializable).
